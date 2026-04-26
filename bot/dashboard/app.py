"""
Streamlit dashboard — Project Takashi.
Run with: streamlit run dashboard/app.py --server.port 8501
"""

import time
import sys
import os
import requests
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from datetime import datetime, timezone, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings

st.set_page_config(
    page_title="Project Takashi",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inside Docker the API is reachable via service name; locally via localhost
API = os.getenv("API_URL", "http://localhost:8000")


# ─── API helpers ──────────────────────────────────────────────────────────────

def _get(endpoint: str, fallback=None):
    try:
        r = requests.get(f"{API}{endpoint}", timeout=3)
        return r.json() if r.ok else fallback
    except Exception:
        return fallback


# ─── Data loading ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_trades() -> pd.DataFrame:
    try:
        from db.session import get_session
        from db.models import Trade
        with get_session() as session:
            if session is None:
                return _demo_trades()
            rows = session.query(Trade).order_by(Trade.id.asc()).all()
            if not rows:
                return _demo_trades()
            return pd.DataFrame([{
                "symbol": r.symbol, "direction": r.direction,
                "entry": r.entry, "exit": r.exit, "size": r.size,
                "pnl": r.pnl or 0.0, "score": r.score,
                "reason": r.reason, "mode": r.mode,
                "opened_at": r.opened_at,
            } for r in rows])
    except Exception:
        return _demo_trades()


def _demo_trades() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    n = 80
    pnl = rng.normal(0.003, 0.012, n)
    now = pd.Timestamp.now(tz="UTC")
    dates = pd.date_range(end=now, periods=n, freq="2h", tz="UTC")
    return pd.DataFrame({
        "symbol": rng.choice(["XRP"], n),
        "direction": "BUY",
        "pnl": pnl,
        "score": rng.integers(5, 9, n),
        "reason": rng.choice(["TP", "SL"], n, p=[0.62, 0.38]),
        "mode": "PAPER",
        "opened_at": dates,
    })


def compute_metrics(df: pd.DataFrame, starting_equity: float = 1_000.0) -> dict:
    pnl = df["pnl"].dropna()
    if len(pnl) == 0:
        return {"total_pnl": 0, "trades": 0, "win_rate": 0, "max_drawdown": 0,
                "profit_factor": 0, "sharpe": 0, "avg_win": 0, "avg_loss": 0,
                "equity_series": [starting_equity], "drawdown_series": [0], "pnl_series": []}
    equity = pnl.cumsum() + starting_equity
    peak = equity.cummax()
    dd = (peak - equity) / peak
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    return {
        "total_pnl": float(pnl.sum()),
        "trades": len(pnl),
        "win_rate": len(wins) / len(pnl),
        "max_drawdown": float(dd.max()),
        "profit_factor": float(wins.sum() / abs(losses.sum())) if losses.sum() != 0 else 0,
        "sharpe": float(pnl.mean() / pnl.std()) if len(pnl) > 1 else 0,
        "avg_win": float(wins.mean()) if len(wins) > 0 else 0,
        "avg_loss": float(losses.mean()) if len(losses) > 0 else 0,
        "equity_series": equity.tolist(),
        "drawdown_series": dd.tolist(),
        "pnl_series": pnl.tolist(),
    }


# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("🎯 Project Takashi")
    st.caption(f"Mode: **{settings.MODE}**")
    st.divider()

    auto_refresh = st.toggle("Auto-refresh (30s)", value=True)
    if st.button("Refresh Now"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption(f"Updated: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")


# ─── Status bar ───────────────────────────────────────────────────────────────

status = _get("/status", {})
bot_running = status.get("running", False)
kill_triggered = status.get("kill_switch_triggered", False)
live_equity = status.get("equity", 0.0)
trade_count = status.get("trade_count", 0)
start_time = status.get("start_time", "")

if kill_triggered:
    st.error("🔴 KILL SWITCH TRIGGERED — Bot halted. Check logs.")
elif bot_running:
    st.success(f"🟢 Bot running | Mode: **{settings.MODE}** | Trades: **{trade_count}**")
else:
    st.warning("🟡 Bot offline — dashboard showing cached data")

# Equity always visible in its own row
eq_col1, eq_col2, eq_col3 = st.columns(3)
eq_col1.metric("Live Equity", f"${live_equity:,.2f}", delta=f"${live_equity - 1_000:+,.2f}" if live_equity else None)
eq_col2.metric("Starting Capital", "$1,000.00")
eq_col3.metric("Return", f"{((live_equity / 1_000) - 1) * 100:+.3f}%" if live_equity else "0.000%")

if start_time:
    try:
        started = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        uptime = datetime.now(timezone.utc) - started
        h, rem = divmod(int(uptime.total_seconds()), 3600)
        m = rem // 60
        st.caption(f"Uptime: {h}h {m}m | Assets: {', '.join(status.get('active_assets', []))}")
    except Exception:
        pass

st.divider()

# ─── Tabs ─────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs(["📊 Overview", "📋 Open Positions", "⚡ Signal Feed", "🤖 ML Status"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    df_all = load_trades()

    scope = st.radio("Time range", ["All time", "Today"], horizontal=True)
    if scope == "Today" and "opened_at" in df_all.columns:
        today = pd.Timestamp.now(tz="UTC").date()
        df = df_all[pd.to_datetime(df_all["opened_at"], utc=True).dt.date == today].copy()
    else:
        df = df_all.copy()

    m = compute_metrics(df)

    # KPI row
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total PnL", f"${m['total_pnl']:.2f}")
    c2.metric("Trades", m["trades"])
    c3.metric("Win Rate", f"{m['win_rate']:.1%}")
    c4.metric("Max Drawdown", f"{m['max_drawdown']:.2%}", delta_color="inverse")
    c5.metric("Profit Factor", f"{m['profit_factor']:.2f}")
    c6.metric("Sharpe", f"{m['sharpe']:.2f}")

    st.divider()

    # Equity + Drawdown
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Equity Curve")
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            y=m["equity_series"], mode="lines",
            line=dict(color="#00cc96", width=2), name="Equity"
        ))
        fig_eq.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_eq, use_container_width=True)

    with col_b:
        st.subheader("Drawdown")
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            y=[-v for v in m["drawdown_series"]], mode="lines",
            fill="tozeroy", line=dict(color="#ef553b", width=1), name="DD"
        ))
        fig_dd.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_dd, use_container_width=True)

    # PnL by asset + Exit reasons
    col_c, col_d = st.columns(2)
    with col_c:
        st.subheader("PnL by Asset")
        by_asset = df.groupby("symbol")["pnl"].sum().reset_index()
        fig_bar = px.bar(by_asset, x="symbol", y="pnl", color="pnl",
                         color_continuous_scale=["#ef553b", "#636efa", "#00cc96"])
        fig_bar.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_d:
        st.subheader("Exit Reasons")
        if "reason" in df.columns and len(df) > 0:
            rc = df["reason"].value_counts().reset_index()
            rc.columns = ["reason", "count"]
            fig_pie = px.pie(rc, names="reason", values="count",
                             color_discrete_sequence=["#00cc96", "#ef553b", "#636efa"])
            fig_pie.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig_pie, use_container_width=True)

    # Trade table
    st.subheader("Recent Trades")
    if len(df) > 0:
        display_df = df.copy().tail(30).sort_index(ascending=False)

        # Format time
        if "opened_at" in display_df.columns:
            display_df["time"] = pd.to_datetime(display_df["opened_at"], utc=True, errors="coerce") \
                .dt.strftime("%m-%d %H:%M")

        # Add running equity column
        pnl_col = df["pnl"].dropna().cumsum() + 1_000
        df2 = df.copy()
        df2["equity"] = pnl_col
        display_df = df2.tail(30).sort_index(ascending=False)
        if "opened_at" in display_df.columns:
            display_df["time"] = pd.to_datetime(display_df["opened_at"], utc=True, errors="coerce") \
                .dt.strftime("%m-%d %H:%M")
        display_df["equity"] = display_df["equity"].map(lambda v: f"${v:,.2f}" if pd.notna(v) else "—")
        display_df["pnl"] = display_df["pnl"].map(lambda v: f"${v:+.4f}" if pd.notna(v) else "—")

        cols = [c for c in ["time", "symbol", "direction", "entry", "exit", "pnl", "equity", "score", "reason"]
                if c in display_df.columns]
        st.dataframe(display_df[cols], use_container_width=True)
    else:
        st.info("No trades yet. Signals fire once 30 candles have buffered (~2.5 hrs).")

    # Sidebar avg win/loss
    with st.sidebar:
        st.metric("Avg Win", f"${m['avg_win']:.4f}")
        st.metric("Avg Loss", f"${m['avg_loss']:.4f}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — OPEN POSITIONS
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    st.subheader("Open Positions (Paper Broker)")
    pos_data = _get("/positions", {})
    positions = pos_data.get("positions", [])

    if positions:
        pos_df = pd.DataFrame(positions)
        pos_df["age"] = pos_df["age_seconds"].apply(
            lambda s: f"{s // 60}m {s % 60}s"
        )
        pos_df["dist_to_tp"] = ((pos_df["tp"] - pos_df["entry"]) / pos_df["entry"] * 100).round(3)
        pos_df["dist_to_sl"] = ((pos_df["entry"] - pos_df["sl"]) / pos_df["entry"] * 100).round(3)

        display = pos_df[["id", "symbol", "entry", "size", "tp", "sl", "dist_to_tp", "dist_to_sl", "age"]]
        display.columns = ["ID", "Symbol", "Entry", "Size", "TP", "SL", "TP %", "SL %", "Age"]
        st.dataframe(display, use_container_width=True)

        st.caption(f"{len(positions)} open position(s)")
    else:
        st.info("No open positions right now.")
        if not bot_running:
            st.warning("Bot is not running — start it to begin paper trading.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — SIGNAL FEED
# ══════════════════════════════════════════════════════════════════════════════

with tab3:
    st.subheader("Live Signal Feed")
    st.caption("Every market evaluation — passed signals and vetoed ones.")

    sig_data = _get("/signals/recent", {})
    signals = sig_data.get("signals", [])

    if signals:
        rows = []
        for s in signals:
            ts = s.get("timestamp", "")
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                ts_fmt = dt.strftime("%H:%M:%S")
            except Exception:
                ts_fmt = ts

            valid = s.get("valid", False)
            score = s.get("score", 0)
            rows.append({
                "Time": ts_fmt,
                "Asset": s.get("asset", ""),
                "Direction": s.get("direction") or "—",
                "Score": score,
                "Status": "✅ FIRED" if valid else "❌ Vetoed",
                "Price": s.get("price", 0.0),
            })

        sig_df = pd.DataFrame(rows)

        fired = sig_df[sig_df["Status"] == "✅ FIRED"]
        vetoed = sig_df[sig_df["Status"] == "❌ Vetoed"]

        m1, m2, m3 = st.columns(3)
        m1.metric("Signals Evaluated", len(sig_df))
        m2.metric("Fired", len(fired))
        m3.metric("Vetoed", len(vetoed))

        st.dataframe(
            sig_df.style.apply(
                lambda col: ["color: #00cc96" if v == "✅ FIRED" else "color: #ef553b"
                             for v in col] if col.name == "Status" else [""] * len(col),
                axis=0,
            ),
            use_container_width=True,
            height=420,
        )
    else:
        st.info("No signals yet — the bot needs ~30 candles before evaluation starts (~2.5 hrs on 5m bars).")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — ML STATUS
# ══════════════════════════════════════════════════════════════════════════════

with tab4:
    st.subheader("ML Model Status")

    ml = _get("/ml/status", {})
    trained = ml.get("trained", False)
    samples = ml.get("samples", 0)
    top_features = ml.get("top_features", {})
    last_retrain = ml.get("last_retrain")
    threshold = 100

    # Status card
    if trained:
        st.success("🤖 Model is **trained and active** — ML veto layer is ON")
    else:
        st.warning("⏳ Model not yet trained — running on **rules only** (pass-through mode)")

    col1, col2, col3 = st.columns(3)
    col1.metric("Training Samples", f"{samples} / {threshold}")
    col2.metric("Status", "Active ✅" if trained else "Warming up ⏳")
    col3.metric("Confidence Threshold", "55%")

    # Progress bar to 100 samples
    if not trained:
        progress = min(samples / threshold, 1.0)
        st.progress(progress, text=f"Collecting samples: {samples}/{threshold} ({progress:.0%})")
        eta_bars = max(0, threshold - samples)
        st.caption(f"Estimated time to first training: ~{eta_bars * 5} minutes at current rate")

    if last_retrain:
        try:
            dt = datetime.fromisoformat(last_retrain.replace("Z", "+00:00"))
            st.caption(f"Last retrain: {dt.strftime('%Y-%m-%d %H:%M UTC')}")
        except Exception:
            pass

    st.divider()

    # Feature importance chart
    st.subheader("Feature Importance")
    if top_features:
        feat_df = pd.DataFrame(
            sorted(top_features.items(), key=lambda x: x[1], reverse=True),
            columns=["Feature", "Importance"]
        )
        fig_feat = px.bar(
            feat_df, x="Importance", y="Feature", orientation="h",
            color="Importance", color_continuous_scale=["#636efa", "#00cc96"],
        )
        fig_feat.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_feat, use_container_width=True)
    else:
        st.info("Feature importance available after first model training.")
        st.markdown("""
**Features the model watches:**
| Feature | Measures |
|---|---|
| `rsi` | Momentum — oversold/overbought |
| `imbalance` | Order book buy vs sell pressure |
| `ma25_dev` | % distance from 25-bar moving average |
| `vol_ratio` | Current volume vs 20-bar average |
| `vwap_dev` | % distance from VWAP |
| `return` | Last bar price change |
| `volatility` | 20-bar rolling std dev |
| `atr` | Average true range |
| `spread` | Bid-ask spread |
""")

    st.divider()
    st.subheader("How ML + Rules Work Together")
    st.markdown("""
```
Every tick:
  Rule engine scores signal (RSI, volume, panic drop, imbalance…)
        ↓
  Score ≥ 5?  →  Build 9-feature vector from price + order book
        ↓
  ML model trained?
    YES → predict(features) → confidence ≥ 55%?
            YES → ✅ TRADE FIRES
            NO  → ❌ ML vetoes signal
    NO  → ✅ Pass-through (rules only)
```
**Both layers must agree.** ML raises the bar once trained — fewer trades, higher quality.
""")


# ─── Auto-refresh ─────────────────────────────────────────────────────────────

if auto_refresh:
    time.sleep(30)
    st.cache_data.clear()
    st.rerun()
