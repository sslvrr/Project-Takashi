"""
Alert dispatcher — routes alerts to Telegram and logs.
send_alert() is the universal alert call used throughout the system.
"""

from core.logger import logger


def send_alert(message: str, level: str = "INFO") -> None:
    logger.log(level, f"[alert] {message}")
    try:
        from core.telegram import send_telegram
        send_telegram(message)
    except Exception as exc:
        logger.debug(f"[alert] Telegram delivery failed: {exc}")
