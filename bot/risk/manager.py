"""
Risk manager — position sizing and trade permission gate.
Called before every execution decision.
"""

from config.settings import settings
from core.logger import logger


def position_size(
    balance: float,
    price: float,
    risk_pct: float | None = None,
    stop_pct: float | None = None,
) -> float:
    """
    Risk-based position size.
    size = (balance × risk_pct) / stop_pct
    Returns units (e.g. XRP amount or forex lots).
    """
    r = risk_pct or settings.RISK_PER_TRADE
    s = stop_pct or settings.STOP_LOSS_PCT
    if price <= 0 or s <= 0:
        return 0.0
    dollar_risk = balance * r
    units = dollar_risk / (price * s)
    return round(units, 6)


def lot_size_fx(
    balance: float,
    risk_pct: float | None = None,
    stop_pips: float = 20.0,
    pip_value: float = 10.0,
) -> float:
    """
    Forex lot size calculator.
    stop_pips: stop loss in pips
    pip_value: value per pip per standard lot (default $10 for EURUSD)
    Returns standard lots (round to 2 decimals).
    """
    r = risk_pct or settings.RISK_PER_TRADE
    dollar_risk = balance * r
    lots = dollar_risk / (stop_pips * pip_value)
    return max(0.01, round(lots, 2))


def allow_trade(last_trades: list[float], max_consecutive_losses: int = 3) -> bool:
    """
    Cluster filter: halt trading after N consecutive losses.
    Prevents revenge trading and sideways chop bleeding.
    """
    if not last_trades:
        return True
    recent = last_trades[-max_consecutive_losses:]
    losses = sum(1 for t in recent if t < 0)
    if losses >= max_consecutive_losses:
        logger.warning(f"[risk] {losses} consecutive losses detected — trade blocked.")
        return False
    return True


def check_daily_loss(daily_pnl: float, balance: float) -> bool:
    """Return True if daily loss limit has NOT been breached."""
    if balance <= 0:
        return False
    loss_pct = abs(min(daily_pnl, 0)) / balance
    if loss_pct >= settings.MAX_DAILY_LOSS:
        logger.warning(f"[risk] Daily loss limit reached: {loss_pct:.2%}")
        return False
    return True


def check_max_positions(open_positions: int) -> bool:
    """Return True if adding another position is within limit."""
    if open_positions >= settings.MAX_CONCURRENT_POSITIONS:
        logger.debug(f"[risk] Max positions ({settings.MAX_CONCURRENT_POSITIONS}) reached.")
        return False
    return True
