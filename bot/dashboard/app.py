"""
Streamlit dashboard — Project Takashi v3.
Run with: streamlit run dashboard/app.py --server.port 8501
"""

import time
import sys
import os
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import settings
from db.session import init_db, is_available as _db_available

# Initialize DB engine once per process (Streamlit reruns the script but
# Python modules are only imported once, so this is safe to guard with is_available)
if not _db_available():
    init_db()

st.set_page_config(
    page_title="Project Takashi",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

API = os.getenv("API_URL", "http://localhost:8000")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get(endpoint: str, fallback=None):
    try:
        r = requests.get(f"{API}{endpoint}", timeout=4)
        return r.json() if r.ok else fallback
    except Exception:
        return fallback


def _post(endpoint: str) -> bool:
    try:
        r = requests.post(f"{API}{endpoint}", timeout=4)
        return r.ok
    except Exception:
        return False


@st.cache_data(ttl=30)
def load_trades() -> pd.DataFrame:
    try:
        from db.session import get_session
        from db.models import Trade
        with get_session() as session:
            if session is None:
                return pd.DataFrame()
            rows = session.query(Trade).order_by(Trade.id.asc()).all()
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame([{
                "db_id": r.id,
                "symbol": r.symbol, "direction": r.direction,
                "entry": r.entry, "exit": r.exit, "size": r.size,
                "pnl": r.pnl or 0.0, "tp": r.tp, "sl": r.sl,
                "score": r.score, "strategy": r.strategy,
                "r_multiple": r.r_multiple,
                "reason": r.reason, "mode": r.mode,
                "opened_at": r.opened_at, "closed_at": r.closed_at,
            } for r in rows])
    except Exception:
        return pd.DataFrame()


def compute_metrics(df: pd.DataFrame, start: float = 1_000.0) -> dict:
    if df.empty or "pnl" not in df.columns:
        pnl = pd.Series([], dtype=float)
    else:
        pnl = df["pnl"].dropna()
    if len(pnl) == 0:
        return {"total_pnl": 0, "trades": 0, "win_rate": 0, "max_drawdown": 0,
                "profit_factor": 0, "sharpe": 0, "avg_win": 0, "avg_loss": 0,
                "equity_series": [start], "drawdown_series": [0], "pnl_series": []}
    equity = pnl.cumsum() + start
    peak = equity.cummax()
    dd = (peak - equity) / peak
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    return {
        "total_pnl":      float(pnl.sum()),
        "trades":         len(pnl),
        "win_rate":       len(wins) / len(pnl),
        "max_drawdown":   float(dd.max()),
        "profit_factor":  float(wins.sum() / abs(losses.sum())) if losses.sum() != 0 else 0,
        "sharpe":         float(pnl.mean() / pnl.std()) if len(pnl) > 1 else 0,
        "avg_win":        float(wins.mean()) if len(wins) > 0 else 0,
        "avg_loss":       float(losses.mean()) if len(losses) > 0 else 0,
        "equity_series":  equity.tolist(),
        "drawdown_series": dd.tolist(),
        "pnl_series":     pnl.tolist(),
    }


# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("🎯 Project Takashi")
    st.caption(f"Mode: **{settings.MODE}**")
    st.divider()

    auto_refresh = st.toggle("Auto-refresh (30s)", value=True)
    if st.button("🔄 Refresh Now"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.subheader("Bot Controls")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("▶ Start", use_container_width=True):
            ok = _post("/start")
            st.success("Started") if ok else st.error("Failed")
    with col_b:
        if st.button("⏹ Stop", use_container_width=True, type="primary"):
            ok = _post("/stop")
            st.warning("Stopped") if ok else st.error("Failed")

    st.divider()
    st.subheader("Asset Toggle")
    assets_data = _get("/assets", {})
    for asset, enabled in assets_data.items():
        new_val = st.toggle(asset, value=enabled, key=f"asset_{asset}")
        if new_val != enabled:
            try:
                requests.post(f"{API}/assets/toggle",
                              json={"asset": asset, "enabled": new_val}, timeout=3)
            except Exception:
                pass

    st.divider()
    st.caption(f"Updated: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")


# ─── Status bar ───────────────────────────────────────────────────────────────

status = _get("/status", {})
bot_running      = status.get("running", False)
kill_triggered   = status.get("kill_switch_triggered", False)
live_equity      = status.get("equity", 0.0)
trade_count      = status.get("trade_count", 0)
start_time       = status.get("start_time", "")

if kill_triggered:
    st.error("🔴 KILL SWITCH TRIGGERED — Bot halted. Check logs.")
elif bot_running:
    st.success(f"🟢 Bot running | Mode: **{settings.MODE}** | Trades: **{trade_count}**")
else:
    st.warning("🟡 Bot offline — dashboard showing cached data")

eq1, eq2, eq3 = st.columns(3)
eq1.metric("Live Equity", f"${live_equity:,.2f}",
           delta=round(live_equity - 1_000, 2) if live_equity else None)
eq2.metric("Starting Capital", "$1,000.00")
eq3.metric("Return", f"{((live_equity / 1_000) - 1) * 100:+.3f}%" if live_equity else "0.000%")

if start_time:
    try:
        started = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        uptime  = datetime.now(timezone.utc) - started
        h, rem  = divmod(int(uptime.total_seconds()), 3600)
        m       = rem // 60
        st.caption(f"Uptime: {h}h {m}m | Assets: {', '.join(status.get('active_assets', []))}")
    except Exception:
        pass

st.divider()

# ─── Tabs ─────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "📊 Overview", "📋 Positions", "⚡ Signals",
    "🤖 ML", "⚠️ Risk & Health", "🎯 Go-Live", "👥 Investor", "🧬 Strategies",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    df_all = load_trades()
    scope = st.radio("Time range", ["All time", "Today"], horizontal=True)
    if scope == "Today" and "opened_at" in df_all.columns:
        today = pd.Timestamp.now(tz="UTC").date()
        df = df_all[pd.to_datetime(df_all["opened_at"], utc=True, errors="coerce").dt.date == today].copy()
    else:
        df = df_all.copy()

    m = compute_metrics(df)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total PnL",      f"${m['total_pnl']:.2f}")
    c2.metric("Trades",          m["trades"])
    c3.metric("Win Rate",        f"{m['win_rate']:.1%}")
    c4.metric("Max Drawdown",    f"{m['max_drawdown']:.2%}", delta_color="inverse")
    c5.metric("Profit Factor",   f"{m['profit_factor']:.2f}")
    c6.metric("Sharpe",          f"{m['sharpe']:.2f}")

    st.divider()

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Equity Curve")
        fig = go.Figure()
        fig.add_trace(go.Scatter(y=m["equity_series"], mode="lines",
                                 line=dict(color="#00cc96", width=2), name="Equity"))
        fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("Drawdown")
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(y=[-v for v in m["drawdown_series"]], mode="lines",
                                  fill="tozeroy", line=dict(color="#ef553b", width=1)))
        fig2.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig2, use_container_width=True)

    col_c, col_d = st.columns(2)
    with col_c:
        st.subheader("PnL by Asset")
        by_asset = df.groupby("symbol")["pnl"].sum().reset_index() if len(df) > 0 else pd.DataFrame({"symbol": [], "pnl": []})
        fig3 = px.bar(by_asset, x="symbol", y="pnl", color="pnl",
                      color_continuous_scale=["#ef553b", "#636efa", "#00cc96"])
        fig3.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig3, use_container_width=True)

    with col_d:
        st.subheader("Exit Reasons")
        if "reason" in df.columns and len(df) > 0:
            rc = df["reason"].value_counts().reset_index()
            rc.columns = ["reason", "count"]
            fig4 = px.pie(rc, names="reason", values="count",
                          color_discrete_sequence=["#00cc96", "#ef553b", "#636efa"])
            fig4.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig4, use_container_width=True)

    # ── Trade History ─────────────────────────────────────────────────────────
    st.subheader("Trade History")
    if len(df) == 0:
        st.info("No closed trades yet — open positions settle here once they hit TP, SL, or manual close.")
    else:
        from zoneinfo import ZoneInfo
        eastern = ZoneInfo("America/New_York")

        tj = df.copy().reset_index(drop=True)

        # Sequential trade ID
        tj["#"] = [f"T-{(i + 1):04d}" for i in range(len(tj))]

        # Time in EST
        tj["Time (EST)"] = (
            pd.to_datetime(tj["opened_at"], utc=True, errors="coerce")
            .dt.tz_convert(eastern)
            .dt.strftime("%-m/%-d, %H:%M")
        )

        # Direction label
        dir_map = {"BUY": "LONG", "SELL": "SHORT"}
        tj["Dir"] = tj["direction"].str.upper().map(dir_map).fillna(tj["direction"].str.upper())

        # Strategy
        tj["Strategy"] = tj["strategy"].fillna("—").str.upper() if "strategy" in tj.columns else "—"

        # Pips: signed price movement in the trade's favour × 10000
        if "entry" in tj.columns and "exit" in tj.columns:
            def _calc_pips(row):
                if pd.isna(row.get("exit")):
                    return "—"
                diff = (row["exit"] - row["entry"]) * 10_000
                if row.get("direction", "BUY") == "SELL":
                    diff = -diff
                return f"{diff:+.1f}"
            tj["Pips"] = tj.apply(_calc_pips, axis=1)
        else:
            tj["Pips"] = "—"

        # R-multiple
        if "r_multiple" in tj.columns:
            tj["R"] = tj["r_multiple"].apply(
                lambda v: f"{v:+.2f}R" if pd.notna(v) else "—"
            )
        else:
            tj["R"] = "—"

        # P&L
        tj["P&L"] = tj["pnl"].apply(lambda v: f"${v:+.2f}" if pd.notna(v) else "—")

        # Score (stored 0-10, display as %)
        if "score" in tj.columns:
            tj["Score"] = tj["score"].apply(
                lambda v: f"{int(v) * 10}%" if pd.notna(v) and v is not None else "—"
            )
        else:
            tj["Score"] = "—"

        # Result
        tj["Result"] = tj["pnl"].apply(
            lambda v: "WIN" if pd.notna(v) and v > 0 else ("LOSS" if pd.notna(v) and v < 0 else "FLAT")
        )

        # Reason label
        reason_map = {"TP": "TARGET", "SL": "STOP", "MANUAL": "MANUAL"}
        if "reason" in tj.columns:
            tj["Reason"] = tj["reason"].str.upper().map(reason_map).fillna(tj["reason"].str.upper())
        else:
            tj["Reason"] = "—"

        # Entry/Exit formatted
        tj["Entry"] = tj["entry"].apply(lambda v: f"{v:.5f}" if pd.notna(v) else "—")
        tj["Exit"]  = tj["exit"].apply(lambda v: f"{v:.5f}" if pd.notna(v) else "—")

        # ── Filters ───────────────────────────────────────────────────────────
        # Row 1: Asset / symbol
        symbols = sorted(tj["symbol"].dropna().unique().tolist()) if "symbol" in tj.columns else []
        symbol_opts = ["All"] + symbols
        f1, f2 = st.columns([3, 7])
        with f1:
            selected_symbol = st.radio(
                "Asset", symbol_opts, horizontal=True,
                key="symbol_filter"
            )

        # Row 2: Strategy / result
        strategies = sorted([s for s in tj["Strategy"].unique() if s not in ("—",)])
        filter_opts = ["All"] + strategies + ["Wins", "Losses"]
        with f2:
            selected = st.radio(
                "Filter", filter_opts, horizontal=True,
                key="trade_filter"
            )

        view = tj.copy()

        # Apply asset filter first
        if selected_symbol != "All":
            view = view[view["symbol"] == selected_symbol]

        # Apply strategy / result filter
        if selected == "Wins":
            view = view[view["Result"] == "WIN"]
        elif selected == "Losses":
            view = view[view["Result"] == "LOSS"]
        elif selected not in ("All",):
            view = view[view["Strategy"] == selected]

        view = view.sort_index(ascending=False)

        display_cols = ["#", "Time (EST)", "symbol", "Strategy", "Dir", "Entry", "Exit",
                        "Pips", "R", "P&L", "Score", "Result", "Reason"]
        # Rename symbol for display
        view = view.rename(columns={"symbol": "Asset"})
        display_cols = ["#", "Time (EST)", "Asset", "Strategy", "Dir", "Entry", "Exit",
                        "Pips", "R", "P&L", "Score", "Result", "Reason"]

        # Row colour: green tint for WIN, red tint for LOSS
        def _row_color(row):
            if row["Result"] == "WIN":
                return ["background-color: rgba(0,204,150,0.12)"] * len(row)
            if row["Result"] == "LOSS":
                return ["background-color: rgba(239,85,59,0.12)"] * len(row)
            return [""] * len(row)

        styled = view[display_cols].style.apply(_row_color, axis=1)
        st.dataframe(styled, use_container_width=True, hide_index=True)

        # ── Footer summary ────────────────────────────────────────────────────
        w = len(view[view["Result"] == "WIN"])
        l = len(view[view["Result"] == "LOSS"])
        wr = w / len(view) * 100 if len(view) > 0 else 0.0
        view_pnl = view["pnl"].sum()
        total_all = tj["pnl"].sum()
        st.caption(
            f"Showing {len(view)} trades | {w}W {l}L | WR {wr:.1f}% | "
            f"Filtered P&L ${view_pnl:+.2f} | All-time P&L ${total_all:+.2f}"
        )

    with st.sidebar:
        st.metric("Avg Win",  f"${m['avg_win']:.4f}")
        st.metric("Avg Loss", f"${m['avg_loss']:.4f}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — OPEN POSITIONS
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    st.subheader("Open Positions (Paper Broker)")
    pos_data  = _get("/positions", {})
    positions = pos_data.get("positions", [])

    if positions:
        st.caption(f"{len(positions)} open position(s) — refreshes every 30s")

        for p in positions:
            entry     = p.get("entry", 0)
            current   = p.get("current_price", 0)
            tp        = p.get("tp", 0)
            sl        = p.get("sl", 0)
            size      = p.get("size", 0)
            upnl      = p.get("unrealized_pnl", 0)
            age_s     = p.get("age_seconds", 0)
            direction = p.get("direction", "BUY")
            age_str   = f"{age_s // 60}m {age_s % 60}s"
            if entry:
                upnl_pct = ((current - entry) / entry * 100) if direction != "SELL" \
                           else ((entry - current) / entry * 100)
            else:
                upnl_pct = 0
            pos_id  = p.get("id", "")

            pnl_color = "🟢" if upnl >= 0 else "🔴"

            with st.container(border=True):
                c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 2, 2, 2, 1])
                c1.metric("Symbol",      f"{p.get('symbol', '')} ({direction})")
                c2.metric("Entry",       f"${entry:.5f}")
                c3.metric("Current",     f"${current:.5f}", delta=f"{upnl_pct:+.3f}%")
                c4.metric("Unreal. PnL", f"{pnl_color} ${upnl:+.4f}")
                c5.metric("Age",         age_str)
                if c6.button("✕", key=f"close_{pos_id}", help="Close at market price"):
                    ok = _post(f"/positions/{pos_id}/close")
                    if ok:
                        st.warning(f"Close requested for {pos_id} — executes within 5s")
                        st.rerun()
                    else:
                        st.error("Close failed")

                # Visual: where is current price between SL and TP?
                if direction != "SELL" and tp > sl > 0:
                    price_range = tp - sl
                    pos_in_range = max(0.0, min(1.0, (current - sl) / price_range))
                    st.progress(pos_in_range,
                                text=f"SL ${sl:.5f}  ←  current ${current:.5f}  →  TP ${tp:.5f}")
                elif direction == "SELL" and sl > tp > 0:
                    price_range = sl - tp
                    pos_in_range = max(0.0, min(1.0, (sl - current) / price_range))
                    st.progress(pos_in_range,
                                text=f"TP ${tp:.5f}  ←  current ${current:.5f}  →  SL ${sl:.5f}")

                col_info1, col_info2, col_info3 = st.columns(3)
                col_info1.caption(f"Size: {size}")
                if direction != "SELL":
                    col_info2.caption(f"TP dist: +{((tp - entry)/entry*100):.2f}%")
                    col_info3.caption(f"SL dist: -{((entry - sl)/entry*100):.2f}%")
                else:
                    col_info2.caption(f"TP dist: -{((entry - tp)/entry*100):.2f}%")
                    col_info3.caption(f"SL dist: +{((sl - entry)/entry*100):.2f}%")
    else:
        st.info("No open positions right now.")
        st.caption("Positions appear here the moment the bot enters a paper trade. Each card updates every 30s with live price and unrealized P&L.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — SIGNAL FEED
# ══════════════════════════════════════════════════════════════════════════════

with tab3:
    st.subheader("Live Signal Feed")
    st.caption("Every market evaluation — passed and vetoed.")

    sig_data = _get("/signals/recent", {})
    signals  = sig_data.get("signals", [])

    if signals:
        rows = []
        for s in signals:
            try:
                dt = datetime.fromisoformat(s.get("timestamp", "").replace("Z", "+00:00"))
                ts = dt.strftime("%H:%M:%S")
            except Exception:
                ts = "—"
            rows.append({
                "Time":      ts,
                "Asset":     s.get("asset", ""),
                "Direction": s.get("direction") or "—",
                "Score":     s.get("score", 0),
                "Status":    "✅ FIRED" if s.get("valid") else "❌ Vetoed",
                "Price":     s.get("price", 0.0),
            })
        sig_df = pd.DataFrame(rows)
        m1, m2, m3 = st.columns(3)
        m1.metric("Evaluated", len(sig_df))
        m2.metric("Fired",     len(sig_df[sig_df["Status"] == "✅ FIRED"]))
        m3.metric("Vetoed",    len(sig_df[sig_df["Status"] == "❌ Vetoed"]))
        st.dataframe(sig_df, use_container_width=True, height=420)
    else:
        st.info("No signals yet — ~2.5 hrs of candles needed.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — ML STATUS
# ══════════════════════════════════════════════════════════════════════════════

with tab4:
    st.subheader("ML Model Status")
    ml       = _get("/ml/status", {})
    trained  = ml.get("trained", False)
    samples  = ml.get("samples", 0)
    top_feat = ml.get("top_features", {})
    threshold = 100

    if trained:
        st.success("🤖 Model **trained and active** — ML veto layer ON")
    else:
        st.warning("⏳ Model not yet trained — **rules only** (pass-through mode)")

    c1, c2, c3 = st.columns(3)
    c1.metric("Training Samples", f"{samples} / {threshold}")
    c2.metric("Status", "Active ✅" if trained else "Warming up ⏳")
    c3.metric("Confidence Threshold", "55%")

    if not trained:
        st.progress(min(samples / threshold, 1.0),
                    text=f"Collecting samples: {samples}/{threshold} ({min(samples/threshold,1)*100:.0f}%)")
        st.caption(f"ETA to first train: ~{max(0, threshold - samples) * 5} minutes")

    if ml.get("last_retrain"):
        try:
            dt = datetime.fromisoformat(ml["last_retrain"].replace("Z", "+00:00"))
            st.caption(f"Last retrain: {dt.strftime('%Y-%m-%d %H:%M UTC')}")
        except Exception:
            pass

    st.divider()
    st.subheader("Feature Importance")
    if top_feat:
        feat_df = pd.DataFrame(sorted(top_feat.items(), key=lambda x: x[1], reverse=True),
                               columns=["Feature", "Importance"])
        fig_f = px.bar(feat_df, x="Importance", y="Feature", orientation="h",
                       color="Importance", color_continuous_scale=["#636efa", "#00cc96"])
        fig_f.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_f, use_container_width=True)
    else:
        st.info("Feature importance available after first model training.")
        st.markdown("""
| Feature | Measures |
|---|---|
| `rsi` | Momentum — oversold/overbought |
| `imbalance` | Order book buy vs sell pressure |
| `ma25_dev` | % distance from 25-bar MA |
| `vol_ratio` | Volume vs 20-bar average |
| `vwap_dev` | % distance from VWAP |
| `return` | Last bar price change |
| `volatility` | 20-bar rolling std dev |
| `atr` | Average true range |
| `spread` | Bid-ask spread |
""")

    st.divider()
    st.markdown("""
**How it works:**
```
Score ≥ 5  →  Build 9-feature vector
                    ↓
         Model trained?
           YES → confidence ≥ 55% → ✅ TRADE
                 confidence < 55% → ❌ vetoed
           NO  → ✅ pass-through (rules only)
```
""")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — RISK & HEALTH
# ══════════════════════════════════════════════════════════════════════════════

with tab5:
    col_left, col_right = st.columns(2)

    # ── Health ──
    with col_left:
        st.subheader("System Health")
        health = _get("/health/detail", {})
        alive  = health.get("alive", False)
        secs   = health.get("seconds_since_heartbeat", 0)

        if alive:
            st.success(f"💚 Engine alive — last heartbeat {secs:.0f}s ago")
        else:
            st.error(f"💀 Engine stalled — {secs:.0f}s since last heartbeat")

        h1, h2 = st.columns(2)
        h1.metric("Heartbeat Age",  f"{secs:.0f}s")
        h2.metric("Bot Running",    "Yes ✅" if bot_running else "No ❌")

    # ── Risk Summary ──
    with col_right:
        st.subheader("Risk Snapshot")
        risk = _get("/risk/summary", {})
        r1, r2, r3 = st.columns(3)
        r1.metric("Max Drawdown",    f"{risk.get('max_drawdown', 0):.2%}", delta_color="inverse")
        r2.metric("Open Positions",  f"{risk.get('open_positions', 0)} / {risk.get('max_positions', 3)}")
        r3.metric("Daily Loss Used", f"{risk.get('daily_loss_used_pct', 0):.1f}%", delta_color="inverse")

        exposure = risk.get("exposure_by_asset", {})
        if exposure:
            st.markdown("**Exposure by asset:**")
            for sym, sz in exposure.items():
                st.write(f"- {sym}: `{sz}`")
        else:
            st.caption("No open exposure.")

        # Daily loss gauge
        used = risk.get("daily_loss_used_pct", 0)
        st.progress(min(used / 100, 1.0),
                    text=f"Daily loss limit: {used:.1f}% used of {risk.get('daily_loss_limit', 0.05):.0%}")

    st.divider()

    # ── Latency ──
    col_lat, col_arb = st.columns(2)

    with col_lat:
        st.subheader("Pipeline Latency")
        lat = _get("/latency", {})
        if lat:
            lat_df = pd.DataFrame(
                sorted(lat.items(), key=lambda x: x[1], reverse=True),
                columns=["Function", "Avg (ms)"]
            )
            lat_df["Avg (ms)"] = lat_df["Avg (ms)"].round(2)
            fig_lat = px.bar(lat_df, x="Avg (ms)", y="Function", orientation="h",
                             color="Avg (ms)", color_continuous_scale=["#00cc96", "#ef553b"])
            fig_lat.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0),
                                  yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig_lat, use_container_width=True)
        else:
            st.info("Latency data accumulates as functions are called.")

    # ── Arbitrage ──
    with col_arb:
        st.subheader("Arbitrage Monitor")
        st.caption("Coinbase vs Kraken — XRP/USD")
        arb = _get("/arbitrage", {})
        if arb and not arb.get("error"):
            a1, a2, a3 = st.columns(3)
            a1.metric("Coinbase",    f"${arb.get('coinbase', 0):.4f}")
            a2.metric("Kraken",      f"${arb.get('kraken', 0):.4f}")
            a3.metric("Spread",      f"{arb.get('spread_pct', 0):.4f}%")

            opp = arb.get("opportunity", False)
            if opp:
                st.warning("⚡ Arbitrage opportunity detected (>0.2% spread)")
            else:
                st.success("✅ Prices in sync — no arbitrage")

            # Spread gauge
            spread = arb.get("spread_pct", 0)
            st.progress(min(spread / 0.5, 1.0),
                        text=f"Spread: {spread:.4f}% (flag at 0.2%)")
        else:
            st.info("Fetching cross-exchange prices...")
            if arb and arb.get("error"):
                st.caption(f"Error: {arb['error']}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — GO-LIVE GATE
# ══════════════════════════════════════════════════════════════════════════════

with tab6:
    st.subheader("🎯 Go-Live Deployment Gate")
    st.caption("All 5 conditions must be green before switching to LIVE mode.")

    gl = _get("/go-live/status", {})
    ready   = gl.get("ready", False)
    reasons = gl.get("reasons", [])
    metrics = gl.get("metrics", {})

    GATES = [
        ("≥ 50 paper trades",         metrics.get("trades", 0) >= 50,
         f"{metrics.get('trades', 0)} / 50"),
        ("Win rate > 55%",             metrics.get("win_rate", 0) > 0.55,
         f"{metrics.get('win_rate', 0):.1%}"),
        ("Total PnL positive",         metrics.get("pnl", 0) > 0,
         f"${metrics.get('pnl', 0):.4f}"),
        ("Max drawdown < 15%",         metrics.get("max_drawdown", 1) < 0.15,
         f"{metrics.get('max_drawdown', 0):.2%}"),
        ("Profit factor ≥ 1.2",        metrics.get("profit_factor", 0) >= 1.2,
         f"{metrics.get('profit_factor', 0):.2f}"),
    ]

    gates_met = sum(1 for _, ok, _ in GATES if ok)
    st.progress(gates_met / 5, text=f"{gates_met} / 5 conditions met")

    if ready:
        st.success("✅ **All gates passed — you can go LIVE.** Set `MODE=LIVE` in `.env` and restart.")
    else:
        st.warning("⏳ Not ready for LIVE yet. Keep paper trading.")

    st.divider()

    for label, ok, val in GATES:
        icon = "✅" if ok else "❌"
        cols = st.columns([1, 4, 2])
        cols[0].write(icon)
        cols[1].write(label)
        cols[2].write(f"`{val}`")

    st.divider()

    # Monthly Report
    st.subheader("Monthly Report")
    mr = _get("/monthly/report", {})
    report_text = mr.get("report", "No trades yet.")
    st.code(report_text, language=None)

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("📨 Send to Telegram", use_container_width=True):
            ok = _post("/monthly/send")
            st.success("Sent!") if ok else st.error("Failed — check Telegram config")
    with col_btn2:
        st.caption(f"Based on {mr.get('trades', 0)} trades")

    st.divider()

    st.subheader("How to Go Live")
    st.markdown("""
1. Wait until all 5 gates above are ✅
2. Get Coinbase Advanced Trade API keys from [coinbase.com/settings/api](https://coinbase.com/settings/api)
3. Add to `.env`:
```
MODE=LIVE
COINBASE_API_KEY=your_key
COINBASE_SECRET=your_private_key
```
4. Restart: `docker compose up -d`
5. Watch Telegram — every live trade fires an alert
""")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — INVESTOR VIEW
# ══════════════════════════════════════════════════════════════════════════════

with tab7:
    st.subheader("👥 Investor Dashboard")

    inv_metrics = _get("/metrics/investor", {})

    i1, i2, i3, i4 = st.columns(4)
    i1.metric("Sharpe Ratio",  f"{inv_metrics.get('sharpe', 0):.2f}")
    i2.metric("Max Drawdown",  f"{inv_metrics.get('max_drawdown', 0):.2%}", delta_color="inverse")
    i3.metric("Win Rate",      f"{inv_metrics.get('win_rate', 0):.1%}")
    i4.metric("Profit Factor", f"{inv_metrics.get('profit_factor', 0):.2f}")

    # Equity curve
    eq_series = inv_metrics.get("equity_series", [])
    if eq_series:
        st.subheader("Portfolio Equity Curve")
        fig_inv = go.Figure()
        fig_inv.add_trace(go.Scatter(y=eq_series, mode="lines",
                                     line=dict(color="#00cc96", width=2), name="Equity"))
        fig_inv.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_inv, use_container_width=True)

    st.divider()

    # Investor allocation
    try:
        from db.investors import get_all_investors, allocate_pnl
        investors = get_all_investors()
        if investors:
            st.subheader("Capital Allocation")
            inv_df = pd.DataFrame(investors)
            total = inv_df["capital"].sum()
            inv_df["share_pct"] = (inv_df["capital"] / total * 100).round(2)
            st.dataframe(inv_df, use_container_width=True)

            total_pnl = inv_metrics.get("total_pnl", 0.0)
            if total_pnl:
                dist = allocate_pnl(total_pnl)
                if dist:
                    st.subheader(f"PnL Distribution (Total: ${total_pnl:.4f})")
                    dist_df = pd.DataFrame(
                        [{"Investor": k, "PnL": f"${v:.4f}"} for k, v in dist.items()]
                    )
                    st.dataframe(dist_df, use_container_width=True)
        else:
            st.info("No investors configured yet.")
            st.code('from db.investors import add_investor\nadd_investor("Name", capital=500.0)', language="python")
    except Exception as e:
        st.info(f"Investor DB not available: {e}")

    st.divider()

    st.subheader("Fund Metrics")
    fund_cols = ["sharpe", "sortino", "calmar", "max_drawdown", "win_rate",
                 "profit_factor", "total_pnl", "trades"]
    fund_data = {k: inv_metrics.get(k, "—") for k in fund_cols if k in inv_metrics}
    if fund_data:
        fd_df = pd.DataFrame(fund_data.items(), columns=["Metric", "Value"])
        st.dataframe(fd_df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 8 — STRATEGIES
# ══════════════════════════════════════════════════════════════════════════════

_STATUS_COLOR = {
    "PAPER":       "#1e90ff",
    "DEVELOPMENT": "#ffa500",
    "PAUSED":      "#888888",
    "DISCARD":     "#ff4444",
}
_PIPELINE_COLOR = {
    "ACTIVE":        "#00cc96",
    "BASELINE":      "#888888",
    "PROMOTE":       "#00cc96",
    "ALT_PROMOTE":   "#ffa500",
    "KEEP_IMPROVING":"#1e90ff",
    "FLAGGED_PF":    "#ff9900",
}

_VENOM_REFERENCE = """
## VENOM — ICT Multi-Timeframe Sweep + FVG Strategy

Both bull and bear setups run as independent 8-state machines simultaneously.

### Sequence (Bullish)
```
HTF wick below SSL
  → State 1: track bearish FVG forming on sell-off
  → LTF wick below recent swing low (secondary sweep)
  → State 2→3: bearish FVG confirmed
  → State 3→4: close above bearish FVG top (reclaim = bullish order flow)
  → State 4→5: bullish FVG forms on recovery leg
  → State 5→7: CHOC confirmed (close > b_choc)
  → State 7: retrace into bullish FVG zone → ENTRY
```

### State Machine

| State | Name | CHOC Condition |
|---|---|---|
| 0 | Idle | htf_bull → State 1 |
| 1 | HTF Swept | track bear FVG; ltf sweep → State 2 |
| 2 | LTF Swept | b_bft exists → State 3 immediately |
| 3 | Bear FVG Found | close > b_bft → State 4 |
| 4 | Bear FVG Reclaimed | bull FVG forms → State 5 |
| 5 | Bull FVG Found | close > b_choc → **State 7 (CHOC)** |
| 7 | **CHOC Confirmed** | FVG touch → ENTRY; close < b_choc → State 0 |
| 8 | In Trade | position closed → State 0 |

### Entry & Risk
| Parameter | Value |
|---|---|
| Stop Loss | 10 ticks below LTF sweep wick |
| Take Profit | Entry + (R:R × risk) |
| Default R:R | 2.0 |
| Position Size | 2% equity |

### Timeframes
| LTF Chart | HTF Input | Use Case |
|---|---|---|
| 1H | Daily (D) | Default — swing |
| 15M | 4H | Intraday |
| 5M | 1H | Scalp |

### Backtest (1Y, 1H/D, XAUUSD)
- **7 trades | 71.43% WR | +$137.72 (+1.37%) | Max DD 0.06%**
"""

with tab8:
    h1, h2 = st.columns([5, 2])
    h1.subheader("Strategy Performance")
    h2.caption(f"Updated {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")

    strats_raw = _get("/strategies", {}).get("strategies", [])

    # Load trade data for live metrics (reuse df_all from tab1 scope)
    try:
        _tf_all = load_trades()
    except Exception:
        _tf_all = pd.DataFrame()

    # ── Build HTML performance table ──────────────────────────────────────────
    def _live_metrics(name: str) -> dict:
        if _tf_all.empty or "strategy" not in _tf_all.columns:
            return {"trades": 0, "wr": None, "pnl": None, "rr": None, "exp": None}
        sub = _tf_all[_tf_all["strategy"] == name]
        n = len(sub)
        if n == 0:
            return {"trades": 0, "wr": None, "pnl": None, "rr": None, "exp": None}
        wins   = sub[sub["pnl"] > 0]["pnl"]
        losses = sub[sub["pnl"] < 0]["pnl"]
        wr     = len(wins) / n
        pnl    = sub["pnl"].sum()
        avg_rr = float((wins.mean() / abs(losses.mean()))) if len(wins) > 0 and len(losses) > 0 else None
        exp    = float(sub["pnl"].mean())
        return {"trades": n, "wr": wr, "pnl": pnl, "rr": avg_rr, "exp": exp}

    rows_html = ""
    for s in strats_raw:
        name     = s["name"]
        ver      = s.get("version") or ""
        tf       = s.get("timeframe") or "—"
        assets_s = s.get("assets") or "—"
        status   = s.get("status", "DEVELOPMENT")
        pipeline = s.get("pipeline") or "—"
        bt_wr    = s.get("bt_win_rate")
        bt_pf    = s.get("bt_profit_factor")
        bt_pnl   = s.get("bt_net_pnl")
        bt_n     = s.get("bt_trades")
        lm       = _live_metrics(name)

        sc  = _STATUS_COLOR.get(status, "#888")
        pc  = _PIPELINE_COLOR.get(pipeline.split()[0] if pipeline else "", "#888")

        live_wr  = f"{lm['wr']:.0%}"          if lm["wr"]  is not None else "—"
        live_rr  = f"{lm['rr']:.2f}"          if lm["rr"]  is not None else "—"
        live_pnl = f"${lm['pnl']:+.2f}"       if lm["pnl"] is not None else "—"
        live_exp = f"${lm['exp']:+.2f}"        if lm["exp"] is not None else "—"

        bt_wr_s  = f"bt:{bt_wr*100:.0f}%"     if bt_wr  is not None else ""
        bt_pf_s  = f"PF {bt_pf:.2f}"          if bt_pf  is not None else ""
        bt_pnl_s = f"bt:${bt_pnl:+.2f}"       if bt_pnl is not None else ""
        bt_n_s   = f"{bt_n}t"                  if bt_n   is not None else ""

        pnl_color = "#00cc96" if lm["pnl"] is not None and lm["pnl"] >= 0 else "#ef553b"

        rows_html += f"""
        <tr>
          <td><b>{name}</b><br><small style="color:#888">{ver}</small></td>
          <td>{tf}<br><small style="color:#888">{assets_s}</small></td>
          <td style="text-align:center"><b>{lm['trades']}</b><br><small style="color:#888">{bt_n_s}</small></td>
          <td style="text-align:center"><b>{live_wr}</b><br><small style="color:#888">{bt_wr_s}</small></td>
          <td style="text-align:center">{live_rr}<br><small style="color:#888">{bt_pf_s}</small></td>
          <td style="text-align:center">{live_exp}<br><small style="color:#888">&nbsp;</small></td>
          <td style="text-align:center;color:{pnl_color}"><b>{live_pnl}</b><br><small style="color:#888">{bt_pnl_s}</small></td>
          <td style="text-align:center"><span style="color:{sc};font-weight:700">{status}</span></td>
          <td><span style="color:{pc};font-size:0.8em">{pipeline}</span></td>
        </tr>"""

    table_html = f"""
    <style>
      .strat-table {{ width:100%; border-collapse:collapse; font-family:monospace; font-size:0.85em; }}
      .strat-table th {{ background:#111; color:#666; padding:8px 10px; text-align:left;
                         border-bottom:1px solid #333; letter-spacing:0.08em; font-size:0.75em; }}
      .strat-table td {{ padding:8px 10px; border-bottom:1px solid #1e1e1e; vertical-align:top; color:#ddd; }}
      .strat-table tr:hover td {{ background:#1a1a1a; }}
    </style>
    <table class="strat-table">
      <thead><tr>
        <th>STRATEGY</th><th>TIMEFRAME</th><th>TRADES</th><th>WIN RATE</th>
        <th>AVG R:R</th><th>EXPECTANCY</th><th>GROSS P&L</th><th>STATUS</th><th>PIPELINE</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>"""

    st.markdown(table_html, unsafe_allow_html=True)
    st.divider()

    # ── Per-strategy controls ─────────────────────────────────────────────────
    for s in strats_raw:
        name   = s["name"]
        status = s.get("status", "DEVELOPMENT")
        sc     = _STATUS_COLOR.get(status, "#888")

        with st.expander(f"**{name}** — {s.get('timeframe','?')} | {s.get('assets','?')}"):
            c1, c2, c3 = st.columns([2, 2, 3])

            api_enabled = s.get("enabled", False)
            api_status  = status

            # Sync session state to API value whenever the API value changes
            # (prevents stale session state from sending spurious toggle POSTs on auto-refresh)
            toggle_key   = f"strat_toggle_{name}"
            toggle_track = f"strat_toggle_api_{name}"
            if st.session_state.get(toggle_track) != api_enabled:
                st.session_state[toggle_key]   = api_enabled
                st.session_state[toggle_track] = api_enabled

            status_key   = f"strat_status_{name}"
            status_track = f"strat_status_api_{name}"
            if st.session_state.get(status_track) != api_status:
                st.session_state[status_key]   = api_status
                st.session_state[status_track] = api_status

            # Toggle — only fires POST when user actually clicks
            enabled = c1.toggle("Enabled", key=toggle_key)
            if enabled != api_enabled:
                requests.post(f"{API}/strategies/{name}/toggle",
                              json={"enabled": enabled}, timeout=3)
                st.session_state[toggle_track] = enabled
                st.rerun()

            # Status selector — only fires POST when user actually changes it
            status_opts = ["PAPER", "DEVELOPMENT", "PAUSED", "DISCARD"]
            new_status = c2.selectbox(
                "Status", status_opts,
                index=status_opts.index(api_status) if api_status in status_opts else 1,
                key=status_key,
            )
            if new_status != api_status:
                requests.post(f"{API}/strategies/{name}/status",
                              json={"status": new_status}, timeout=3)
                st.session_state[status_track] = new_status
                st.rerun()

            c3.caption(s.get("description") or "")

            # Backtest summary
            bt_row = []
            if s.get("bt_trades"):     bt_row.append(f"{s['bt_trades']} trades")
            if s.get("bt_win_rate"):   bt_row.append(f"{s['bt_win_rate']*100:.1f}% WR")
            if s.get("bt_profit_factor"): bt_row.append(f"PF {s['bt_profit_factor']:.2f}")
            if s.get("bt_net_pnl"):    bt_row.append(f"${s['bt_net_pnl']:+.2f} net P&L")
            if s.get("bt_max_dd"):     bt_row.append(f"${s['bt_max_dd']:.2f} max DD")
            if bt_row:
                st.caption("**Backtest:** " + " | ".join(bt_row))

            # VENOM full reference
            if name == "VENOM":
                with st.expander("Full Strategy Reference"):
                    st.markdown(_VENOM_REFERENCE)


# ─── Auto-refresh ─────────────────────────────────────────────────────────────

if auto_refresh:
    time.sleep(30)
    st.cache_data.clear()
    st.rerun()
