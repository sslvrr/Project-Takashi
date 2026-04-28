"""
VENOM backtester — fetches historical data via yfinance and replays
the VENOM state machine bar-by-bar.

Usage:
  python -m backtest.venom_bt

Supported symbols:
  XAUUSD → yfinance "GC=F"  (Gold futures, closest proxy)
  EURUSD → yfinance "EURUSD=X"
"""

from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import yfinance as yf
from datetime import datetime, timezone
from strategy.venom import VenomStrategy

# ─── Config ───────────────────────────────────────────────────────────────────

ASSETS = {
    "XAUUSD": "GC=F",
    "EURUSD": "EURUSD=X",
}

TF_CONFIGS = [
    # (label, ltf_yf, htf_yf, ltf_label, htf_label, poll_s, ltf_period, htf_period)
    ("Swing",    "1h",  "1d",  "1H",  "D",   3600, "6mo", "2y"),
    ("Intraday", "15m", "1h",  "15M", "4H",  900,  "60d", "6mo"),
    ("Scalp",    "5m",  "1h",  "5M",  "1H",  300,  "60d", "6mo"),
]

LOOKBACK_DAYS = 180   # 6 months
RR            = 2.0
INITIAL_CAP   = 10_000.0
RISK_PCT      = 0.02  # 2% per trade


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fetch(ticker: str, interval: str, period: str = "6mo") -> pd.DataFrame:
    df = yf.download(ticker, period=period, interval=interval,
                     progress=False, auto_adjust=True)
    if df.empty:
        return df
    # Flatten MultiIndex columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def _simulate_trade(ltf: pd.DataFrame, entry_i: int,
                    direction: str, entry_px: float,
                    sl: float, tp: float, max_bars: int = 500
                    ) -> dict | None:
    """Walk forward from entry_i+1 to find TP or SL hit."""
    for j in range(entry_i + 1, min(entry_i + max_bars + 1, len(ltf))):
        bar = ltf.iloc[j]
        if direction == "BUY":
            if bar["high"] >= tp:
                return {"exit": tp, "result": "WIN",
                        "pnl_pts": tp - entry_px,
                        "bars_held": j - entry_i}
            if bar["low"] <= sl:
                return {"exit": sl, "result": "LOSS",
                        "pnl_pts": sl - entry_px,
                        "bars_held": j - entry_i}
        else:  # SELL
            if bar["low"] <= tp:
                return {"exit": tp, "result": "WIN",
                        "pnl_pts": entry_px - tp,
                        "bars_held": j - entry_i}
            if bar["high"] >= sl:
                return {"exit": sl, "result": "LOSS",
                        "pnl_pts": entry_px - sl,
                        "bars_held": j - entry_i}
    return None  # no exit found within max_bars


def _run_one(asset: str, ticker: str,
             ltf_int: str, htf_int: str,
             ltf_label: str, htf_label: str,
             ltf_period: str = "6mo", htf_period: str = "2y") -> dict:
    print(f"  Fetching {asset} LTF={ltf_label} HTF={htf_label} …", end=" ", flush=True)

    ltf = _fetch(ticker, ltf_int, ltf_period)
    htf = _fetch(ticker, htf_int, htf_period)

    if ltf.empty or htf.empty or len(ltf) < 50:
        print("no data")
        return {"asset": asset, "ltf": ltf_label, "htf": htf_label,
                "trades": 0, "error": "insufficient data"}

    print(f"{len(ltf)} LTF bars, {len(htf)} HTF bars")

    strat  = VenomStrategy(asset=asset, ltf=ltf_label, htf=htf_label, rr=RR)
    trades = []
    equity = INITIAL_CAP
    i_skip = 0  # skip bars while in trade

    for i in range(max(30, strat.htf_sw + 3), len(ltf)):
        if i <= i_skip:
            continue

        ltf_win = ltf.iloc[max(0, i - 200): i + 1]
        bar_time = ltf.index[i]

        # Align HTF: only bars whose close time ≤ current LTF bar time
        htf_win = htf[htf.index <= bar_time].tail(strat.htf_sw + 5)
        if len(htf_win) < strat.htf_sw + 1:
            continue

        sig = strat.process(ltf_win, htf_win)
        if sig is None:
            continue

        # Got a signal — simulate trade
        result = _simulate_trade(ltf, i, sig.direction,
                                 sig.price, sig.sl_price, sig.tp_price)
        strat.on_trade_closed()  # reset state

        if result is None:
            continue

        risk_amt = equity * RISK_PCT
        risk_pts = abs(sig.price - sig.sl_price)
        size     = risk_amt / risk_pts if risk_pts > 0 else 0
        pnl_usd  = result["pnl_pts"] * size
        equity   = max(0, equity + pnl_usd)
        i_skip   = i + result["bars_held"]

        trades.append({
            "asset":     asset,
            "ltf":       ltf_label,
            "htf":       htf_label,
            "direction": sig.direction,
            "entry":     round(sig.price, 5),
            "sl":        round(sig.sl_price, 5),
            "tp":        round(sig.tp_price, 5),
            "exit":      round(result["exit"], 5),
            "result":    result["result"],
            "pnl_pts":   round(result["pnl_pts"], 5),
            "pnl_usd":   round(pnl_usd, 2),
            "bars_held": result["bars_held"],
            "time":      bar_time.strftime("%Y-%m-%d %H:%M"),
        })

    if not trades:
        return {"asset": asset, "ltf": ltf_label, "htf": htf_label,
                "trades": 0, "note": "no setups fired"}

    df_t    = pd.DataFrame(trades)
    wins    = df_t[df_t["result"] == "WIN"]
    losses  = df_t[df_t["result"] == "LOSS"]
    wr      = len(wins) / len(df_t)
    net_pnl = df_t["pnl_usd"].sum()
    pf      = wins["pnl_usd"].sum() / abs(losses["pnl_usd"].sum()) if len(losses) > 0 else float("inf")
    dd      = _max_drawdown(df_t["pnl_usd"].cumsum())

    return {
        "asset":      asset,
        "ltf":        ltf_label,
        "htf":        htf_label,
        "trades":     len(df_t),
        "wins":       len(wins),
        "losses":     len(losses),
        "win_rate":   round(wr, 4),
        "net_pnl":    round(net_pnl, 2),
        "net_pct":    round(net_pnl / INITIAL_CAP * 100, 2),
        "profit_factor": round(pf, 2) if pf != float("inf") else 999,
        "max_dd":     round(dd, 2),
        "detail":     df_t,
    }


def _max_drawdown(equity_series: pd.Series) -> float:
    peak = equity_series.cummax()
    dd   = (peak - equity_series)
    return float(dd.max()) if len(dd) > 0 else 0.0


# ─── Main ─────────────────────────────────────────────────────────────────────

def run_all() -> list[dict]:
    results = []
    for asset, ticker in ASSETS.items():
        print(f"\n{'='*60}")
        print(f"ASSET: {asset}  ({ticker})")
        print('='*60)
        for label, ltf_int, htf_int, ltf_lbl, htf_lbl, _, ltf_per, htf_per in TF_CONFIGS:
            print(f"\n  [{label.upper()}]")
            r = _run_one(asset, ticker, ltf_int, htf_int, ltf_lbl, htf_lbl, ltf_per, htf_per)
            results.append(r)
            _print_result(r)
    return results


def _print_result(r: dict) -> None:
    if r.get("error") or r.get("note"):
        print(f"    → {r.get('error') or r.get('note')}")
        return
    print(f"    Trades:       {r['trades']}  ({r['wins']}W / {r['losses']}L)")
    print(f"    Win Rate:     {r['win_rate']*100:.1f}%")
    print(f"    Net P&L:      ${r['net_pnl']:+,.2f}  ({r['net_pct']:+.2f}%)")
    print(f"    Profit Factor:{r['profit_factor']:.2f}")
    print(f"    Max Drawdown: ${r['max_dd']:,.2f}")
    if "detail" in r and len(r["detail"]) > 0:
        print("\n    Recent trades:")
        cols = ["time", "direction", "entry", "exit", "result", "pnl_usd"]
        print(r["detail"][cols].tail(5).to_string(index=False))


def update_strategy_store(results: list[dict]) -> None:
    """Write best-performing TF result per asset into strategy_configs."""
    try:
        from db.session import init_db, get_session
        from db.models import StrategyConfig
        from datetime import datetime, timezone
        init_db()
        with get_session() as session:
            if session is None:
                return
            row = session.query(StrategyConfig).filter_by(name="VENOM").first()
            if not row:
                return
            valid = [r for r in results if r.get("trades", 0) > 0]
            if not valid:
                return
            best = max(valid, key=lambda x: x.get("win_rate", 0))
            row.bt_win_rate      = float(best["win_rate"])
            row.bt_profit_factor = float(best["profit_factor"])
            row.bt_net_pnl       = float(best["net_pnl"])
            row.bt_max_dd        = float(best.get("max_dd") or 0)
            row.bt_trades        = int(sum(r.get("trades", 0) for r in valid))
            row.updated_at       = datetime.now(timezone.utc)
        print("\n✅ strategy_configs updated with backtest results.")
    except Exception as exc:
        print(f"\n⚠️  Could not update strategy_configs: {exc}")


if __name__ == "__main__":
    print("VENOM Backtester — XAUUSD + EURUSD")
    print(f"Period: 6 months | R:R {RR} | Risk {RISK_PCT*100:.0f}% | Capital ${INITIAL_CAP:,.0f}\n")
    results = run_all()
    update_strategy_store(results)
    print("\nDone.")
