from typing import Optional
"""
Global kill switch — monitors drawdown and halts the entire system
when the portfolio drawdown exceeds the configured threshold.
This is non-negotiable. It runs on every loop iteration.
"""

from config.settings import settings
from core.logger import logger


class KillSwitch:
    def __init__(self, max_drawdown: Optional[float] = None):
        self.max_drawdown = max_drawdown or settings.MAX_DRAWDOWN
        self.peak_equity: float = 0.0
        self.triggered: bool = False
        self._trigger_reason: str = ""

    def update(self, equity: float) -> bool:
        """
        Call with current equity on every loop tick.
        Returns True if kill switch is triggered (STOP TRADING).
        Once triggered it stays latched until manually reset.
        """
        if self.triggered:
            return True

        if equity > self.peak_equity:
            self.peak_equity = equity

        if self.peak_equity <= 0:
            return False

        drawdown = (self.peak_equity - equity) / self.peak_equity

        if drawdown > self.max_drawdown:
            self._trigger_reason = (
                f"Drawdown {drawdown:.2%} exceeded max {self.max_drawdown:.2%}. "
                f"Peak={self.peak_equity:.2f} | Current={equity:.2f}"
            )
            self.triggered = True
            logger.critical(f"[kill_switch] TRIGGERED — {self._trigger_reason}")
            return True

        return False

    def reset(self) -> None:
        """Manual reset — only call after reviewing the situation."""
        logger.warning("[kill_switch] Manual reset. Resuming trading.")
        self.triggered = False
        self.peak_equity = 0.0
        self._trigger_reason = ""

    @property
    def current_drawdown(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return 0.0  # only valid when called with current equity

    @property
    def trigger_reason(self) -> str:
        return self._trigger_reason

    def status(self) -> dict:
        return {
            "triggered": self.triggered,
            "peak_equity": self.peak_equity,
            "max_drawdown_threshold": self.max_drawdown,
            "reason": self._trigger_reason,
        }
