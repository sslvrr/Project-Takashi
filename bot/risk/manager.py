"""
Risk manager — position sizing, trade gates, and direction cooldown.
"""

from datetime import datetime, timezone
from typing import Optional

from config.settings import settings
from core.logger import logger


# ─── Position sizing ──────────────────────────────────────────────────────────

def position_size(
    balance: float,
    price: float,
    risk_pct: Optional[float] = None,
    stop_pct: Optional[float] = None,
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
    risk_pct: Optional[float] = None,
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


# ─── Global trade gates ───────────────────────────────────────────────────────

def allow_trade(last_trades: list[float], max_consecutive_losses: int = 3) -> bool:
    """
    Cluster filter: halt trading after N consecutive losses (any direction).
    """
    if not last_trades:
        return True
    recent = last_trades[-max_consecutive_losses:]
    losses = sum(1 for t in recent if t < 0)
    if losses >= max_consecutive_losses:
        logger.warning(f"[risk] {losses} consecutive losses — trade blocked.")
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


# ─── Per-direction cooldown ───────────────────────────────────────────────────

class DirectionGuard:
    """
    Tracks consecutive losses per direction (BUY / SELL) independently.
    Blocks a failing direction without shutting down the other.
    Resets counters on day change (UTC).
    """

    def __init__(self, max_consec: int = 2):
        self.max_consec      = max_consec
        self._long_losses: int  = 0
        self._short_losses: int = 0
        self._day_key: Optional[str] = None   # "YYYY-MM-DD"

    def _check_day_reset(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        if self._day_key != today:
            self._day_key      = today
            self._long_losses  = 0
            self._short_losses = 0

    def record(self, direction: str, pnl: float) -> None:
        """Call after every closed trade to update loss counters."""
        self._check_day_reset()
        if direction == "BUY":
            if pnl < 0:
                self._long_losses += 1
            else:
                self._long_losses = 0
        else:
            if pnl < 0:
                self._short_losses += 1
            else:
                self._short_losses = 0

    def can_trade(self, direction: str) -> bool:
        """Return False if this direction has hit its consecutive loss limit."""
        self._check_day_reset()
        if direction == "BUY" and self._long_losses >= self.max_consec:
            logger.warning(
                f"[risk] {self._long_losses} consecutive LONG losses — BUY blocked today."
            )
            return False
        if direction == "SELL" and self._short_losses >= self.max_consec:
            logger.warning(
                f"[risk] {self._short_losses} consecutive SHORT losses — SELL blocked today."
            )
            return False
        return True
