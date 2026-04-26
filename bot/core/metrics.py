"""
Institutional-grade performance metrics.
All functions are pure and operate on lists/arrays.
"""

import numpy as np


def sharpe_ratio(returns: list[float], risk_free: float = 0.0) -> float:
    """Annualised Sharpe ratio (assumes daily returns if not stated)."""
    arr = np.array(returns, dtype=float)
    if arr.std() == 0 or len(arr) < 2:
        return 0.0
    return float((arr.mean() - risk_free) / arr.std() * np.sqrt(252))


def sortino_ratio(returns: list[float], risk_free: float = 0.0) -> float:
    arr = np.array(returns, dtype=float)
    downside = arr[arr < 0]
    if len(downside) == 0 or downside.std() == 0:
        return 0.0
    return float((arr.mean() - risk_free) / downside.std() * np.sqrt(252))


def max_drawdown(equity: list[float]) -> float:
    """Return maximum peak-to-trough drawdown as a positive fraction."""
    if not equity:
        return 0.0
    arr = np.array(equity, dtype=float)
    peak = arr[0]
    dd = 0.0
    for x in arr:
        if x > peak:
            peak = x
        if peak > 0:
            dd = max(dd, (peak - x) / peak)
    return float(dd)


def calmar_ratio(annual_return: float, max_dd: float) -> float:
    if max_dd == 0:
        return 0.0
    return annual_return / max_dd


def win_rate(trades: list[float]) -> float:
    if not trades:
        return 0.0
    return sum(1 for t in trades if t > 0) / len(trades)


def profit_factor(trades: list[float]) -> float:
    gains = sum(t for t in trades if t > 0)
    losses = abs(sum(t for t in trades if t < 0))
    return gains / losses if losses > 0 else 0.0


def trade_expectancy(
    win_rate_val: float,
    avg_win: float,
    avg_loss: float,
) -> float:
    """
    Expected value per trade.
    E = (WR × avg_win) − ((1 − WR) × |avg_loss|)
    """
    return (win_rate_val * avg_win) - ((1 - win_rate_val) * abs(avg_loss))


def consistency(monthly_returns: list[float]) -> float:
    """Fraction of months with positive returns."""
    if not monthly_returns:
        return 0.0
    return sum(1 for r in monthly_returns if r > 0) / len(monthly_returns)
