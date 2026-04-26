"""
Risk-specific alert triggers — calls the Telegram notifier when
drawdown, exposure, or loss thresholds are breached.
"""

from core.logger import logger


def risk_check(drawdown: float, threshold: float = 0.10) -> bool:
    """Return True if drawdown exceeds threshold (default 10%)."""
    if drawdown > threshold:
        _send(f"DRAWDOWN ALERT: {drawdown:.2%} exceeded {threshold:.2%}")
        return True
    return False


def daily_loss_alert(daily_pnl: float, balance: float, threshold: float = 0.05) -> None:
    if balance <= 0:
        return
    pct = abs(min(daily_pnl, 0)) / balance
    if pct >= threshold:
        _send(f"DAILY LOSS ALERT: {pct:.2%} loss today (limit={threshold:.2%})")


def _send(msg: str) -> None:
    """Import lazily to avoid circular import at module load time."""
    logger.warning(f"[risk_alerts] {msg}")
    try:
        from core.telegram import send_telegram
        send_telegram(f"⚠️ {msg}")
    except Exception as exc:
        logger.debug(f"[risk_alerts] Telegram send failed: {exc}")
