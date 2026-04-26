"""
Investor-facing report generation.
Aggregates all core metrics into a single report dict.
"""

from core.metrics import (
    sharpe_ratio, max_drawdown, win_rate,
    profit_factor, trade_expectancy, sortino_ratio,
)
from core.performance import get_pnl_series, get_equity_curve


def compute_investor_report() -> dict:
    trades = get_pnl_series()
    equity = get_equity_curve()

    if not trades:
        return {
            "total_pnl": 0.0,
            "trades": 0,
            "win_rate": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown": 0.0,
            "profit_factor": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "expectancy": 0.0,
            "equity_series": equity,
        }

    wr = win_rate(trades)
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t < 0]
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0

    return {
        "total_pnl": round(sum(trades), 4),
        "trades": len(trades),
        "win_rate": round(wr, 4),
        "sharpe": round(sharpe_ratio(trades), 3),
        "sortino": round(sortino_ratio(trades), 3),
        "max_drawdown": round(max_drawdown(equity), 4),
        "profit_factor": round(profit_factor(trades), 3),
        "avg_win": round(avg_win, 6),
        "avg_loss": round(avg_loss, 6),
        "expectancy": round(trade_expectancy(wr, avg_win, avg_loss), 6),
        "equity_series": equity,
    }
