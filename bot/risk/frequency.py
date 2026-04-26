"""
Trade frequency controller — enforces minimum time between trades
per asset to prevent overtrading during choppy conditions.
"""

import time
from core.logger import logger


class FrequencyGuard:
    def __init__(self, min_interval_seconds: int = 60):
        self.min_interval = min_interval_seconds
        self._last_trade: dict[str, float] = {}

    def can_trade(self, asset: str) -> bool:
        now = time.time()
        last = self._last_trade.get(asset, 0.0)
        if now - last < self.min_interval:
            remaining = self.min_interval - (now - last)
            logger.debug(f"[frequency] {asset} cooldown: {remaining:.0f}s remaining.")
            return False
        return True

    def record_trade(self, asset: str) -> None:
        self._last_trade[asset] = time.time()

    def time_since_last(self, asset: str) -> float:
        return time.time() - self._last_trade.get(asset, 0.0)
