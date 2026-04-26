"""
System health monitor — heartbeat tracking and stall detection.
"""

import time
from core.logger import logger

_last_heartbeat: float = time.time()


def heartbeat() -> None:
    global _last_heartbeat
    _last_heartbeat = time.time()


def is_alive(timeout_seconds: int = 120) -> bool:
    return (time.time() - _last_heartbeat) < timeout_seconds


def seconds_since_heartbeat() -> float:
    return time.time() - _last_heartbeat


def check_health(timeout_seconds: int = 120) -> dict:
    alive = is_alive(timeout_seconds)
    if not alive:
        logger.error("[health] System stalled — heartbeat not received.")
        try:
            from core.telegram import send_telegram
            send_telegram("⚠️ System stalled — no heartbeat received!")
        except Exception:
            pass
    return {"alive": alive, "seconds_since_heartbeat": seconds_since_heartbeat()}
