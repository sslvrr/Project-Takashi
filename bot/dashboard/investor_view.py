"""
Investor-facing Streamlit dashboard — fund KPIs, monthly returns, capital allocation.
Run separately: streamlit run dashboard/investor_view.py --server.port 8502
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.investors import get_all_investors, allocate_pnl
from core.investor_metrics import compute_investor_report

st.set_page_config(page_title="Investor Dashboard", layout="wide")
st.title("📈 Project Takashi — Investor Report")


# ─── Metrics ─────────────────────────────────────────────────────────────────

report = compute_investor_report()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Sharpe Ratio", f"{report.get('sharpe', 0):.2f}")
c2.metric("Max Drawdown", f"{report.get('max_drawdown', 0):.2%}")
c3.metric("Win Rate", f"{report.get('win_rate', 0):.1%}")
c4.metric("Profit Factor", f"{report.get('profit_factor', 0):.2f}")

st.divider()

# ─── Equity curve ────────────────────────────────────────────────────────────

equity = report.get("equity_series", [])
if equity:
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=equity, mode="lines", name="Portfolio Equity",
                             line=dict(color="#00cc96", width=2)))
    fig.update_layout(title="Equity Curve", height=350)
    st.plotly_chart(fig, use_container_width=True)

# ─── Investor allocation ─────────────────────────────────────────────────────

st.subheader("Capital Allocation")
investors = get_all_investors()
if investors:
    inv_df = pd.DataFrame(investors)
    total = inv_df["capital"].sum()
    inv_df["share_pct"] = (inv_df["capital"] / total * 100).round(2)
    st.dataframe(inv_df, use_container_width=True)

    # PnL distribution
    total_pnl = report.get("total_pnl", 0.0)
    dist = allocate_pnl(total_pnl)
    if dist:
        st.subheader(f"PnL Distribution (Total: ${total_pnl:.2f})")
        dist_df = pd.DataFrame(
            [{"Investor": k, "PnL": f"${v:.4f}"} for k, v in dist.items()]
        )
        st.dataframe(dist_df, use_container_width=True)
else:
    st.info("No investors configured. Add via `db.investors.add_investor()`.")
