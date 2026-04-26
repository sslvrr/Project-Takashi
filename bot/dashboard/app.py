"""
Streamlit trading dashboard — Project Takashi.
Run with: streamlit run dashboard/app.py --server.port 8501

Reads from PostgreSQL for live data. Falls back gracefully if DB unavailable.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timezone
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings
from core.logger import logger

st.set_page_config(
    page_title="Project Takashi",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)


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
                "id": r.id,
                "symbol": r.symbol,
                "direction": r.direction,
                "entry": r.entry,
                "exit": r.exit,
                "size": r.size,
                "pnl": r.pnl or 0.0,
                "score": r.score,
                "reason": r.reason,
                "mode": r.mode,
                "opened_at": r.opened_at,
            } for r in rows])
    except Exception:
        return _demo_trades()


def _demo_trades() -> pd.DataFrame:
    """Synthetic demo data when DB is unavailable."""
    rng = np.random.default_rng(42)
    n = 80
    pnl = rng.normal(0.003, 0.012, n)
    return pd.DataFrame({
        "symbol": rng.choice(["XRP", "EURUSD"], n),
        "direction": "BUY",
        "pnl": pnl,
        "score": rng.integers(5, 9, n),
        "reason": rng.choice(["TP", "SL"], n, p=[0.62, 0.38]),
        "mode": "PAPER",
    })


# ─── Metrics computation ──────────────────────────────────────────────────────

def compute_metrics(df: pd.DataFrame) -> dict:
    pnl = df["pnl"].dropna()
    equity = pnl.cumsum() + 10_000
    peak = equity.cummax()
    drawdown_series = (peak - equity) / peak
    max_dd = float(drawdown_series.max())
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    win_rate = len(wins) / len(pnl) if len(pnl) > 0 else 0
    avg_win = float(wins.mean()) if len(wins) > 0 else 0
    avg_loss = float(losses.mean()) if len(losses) > 0 else 0
    profit_factor = (wins.sum() / abs(losses.sum())) if losses.sum() != 0 else 0
    sharpe = (float(pnl.mean()) / float(pnl.std())) if len(pnl) > 1 else 0
    return {
        "total_pnl": float(pnl.sum()),
        "trades": len(pnl),
        "win_rate": win_rate,
        "max_drawdown": max_dd,
        "profit_factor": profit_factor,
        "sharpe": sharpe,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "equity_series": equity.tolist(),
        "drawdown_series": drawdown_series.tolist(),
        "pnl_series": pnl.tolist(),
    }


# ─── Layout ───────────────────────────────────────────────────────────────────

st.title("🎯 Project Takashi — Trading System Monitor")
st.caption(f"Mode: **{settings.MODE}** | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

df = load_trades()
m = compute_metrics(df)

# ─── KPI row ─────────────────────────────────────────────────────────────────

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total PnL", f"${m['total_pnl']:.2f}", delta_color="normal")
c2.metric("Trades", m["trades"])
c3.metric("Win Rate", f"{m['win_rate']:.1%}")
c4.metric("Max Drawdown", f"{m['max_drawdown']:.2%}", delta_color="inverse")
c5.metric("Profit Factor", f"{m['profit_factor']:.2f}")
c6.metric("Sharpe Ratio", f"{m['sharpe']:.2f}")

st.divider()

# ─── Equity curve + Drawdown ─────────────────────────────────────────────────

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Equity Curve")
    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(
        y=m["equity_series"], mode="lines",
        name="Equity", line=dict(color="#00cc96", width=2)
    ))
    fig_eq.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig_eq, use_container_width=True)

with col_b:
    st.subheader("Drawdown")
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(
        y=[-v for v in m["drawdown_series"]], mode="lines",
        fill="tozeroy", name="Drawdown", line=dict(color="#ef553b", width=1)
    ))
    fig_dd.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig_dd, use_container_width=True)

# ─── Asset breakdown ──────────────────────────────────────────────────────────

col_c, col_d = st.columns(2)

with col_c:
    st.subheader("PnL by Asset")
    by_asset = df.groupby("symbol")["pnl"].sum().reset_index()
    fig_bar = px.bar(by_asset, x="symbol", y="pnl", color="pnl",
                     color_continuous_scale=["#ef553b", "#636efa", "#00cc96"])
    fig_bar.update_layout(height=280, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig_bar, use_container_width=True)

with col_d:
    st.subheader("Exit Reason Distribution")
    if "reason" in df.columns:
        reason_counts = df["reason"].value_counts().reset_index()
        reason_counts.columns = ["reason", "count"]
        fig_pie = px.pie(reason_counts, names="reason", values="count",
                         color_discrete_sequence=["#00cc96", "#ef553b", "#636efa"])
        fig_pie.update_layout(height=280, margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(fig_pie, use_container_width=True)

# ─── Recent trade log ────────────────────────────────────────────────────────

st.subheader("Recent Trades")
display_cols = [c for c in ["symbol", "direction", "entry", "exit", "pnl", "score", "reason", "mode"]
                if c in df.columns]
st.dataframe(
    df[display_cols].tail(30).sort_index(ascending=False),
    use_container_width=True,
)

# ─── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("System")
    st.info(f"Mode: **{settings.MODE}**")
    st.metric("Avg Win", f"${m['avg_win']:.4f}")
    st.metric("Avg Loss", f"${m['avg_loss']:.4f}")
    if st.button("Refresh"):
        st.cache_data.clear()
        st.rerun()
