"""
Equity curve control — adaptive risk-on/risk-off based on recent
system performance. Shuts off trading when recent performance is negative.
"""


def equity_filter(equity_curve: list[float], lookback: int = 10) -> bool:
    """
    Return True (allow trading) only if the sum of the last `lookback`
    PnL values is positive. Keeps risk off during drawdown runs.
    """
    if len(equity_curve) < lookback:
        return True   # Not enough history — allow trading
    recent = equity_curve[-lookback:]
    return sum(recent) > 0


def rolling_return(equity_series: list[float], n: int = 20) -> float:
    """Return the n-period rolling return as a percentage."""
    if len(equity_series) < n + 1:
        return 0.0
    start = equity_series[-(n + 1)]
    end = equity_series[-1]
    if start <= 0:
        return 0.0
    return (end - start) / start * 100
