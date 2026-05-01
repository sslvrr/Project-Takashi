"""
Global kill switch — three independent halt tiers:
  1. Trail DD (catastrophic, latching) — kills system when drawdown > max_drawdown
  2. Daily halt (timed, 24h) — triggered when daily loss >= MAX_DAILY_LOSS
  3. Weekly halt (timed, to next Monday) — triggered when weekly loss >= WEEKLY_HALT_PCT
"""

import time
from datetime import datetime, timezone
from typing import Optional

from config.settings import settings
from core.logger import logger

WEEKLY_HALT_PCT = 0.06   # 6% weekly loss triggers halt


class KillSwitch:
    def __init__(self, max_drawdown: Optional[float] = None):
        self.max_drawdown    = max_drawdown or settings.MAX_DRAWDOWN
        self.peak_equity: float = 0.0
        self.triggered: bool = False
        self._trigger_reason: str = ""
        self._last_equity: float = 0.0

        # Daily halt
        self._day_start_eq: float    = 0.0
        self._day_key: Optional[str] = None          # "YYYY-MM-DD"
        self._daily_halted_until: float = 0.0        # unix ts

        # Weekly halt
        self._week_start_eq: float    = 0.0
        self._week_key: Optional[str] = None         # "YYYY-Www"
        self._weekly_halted_until: float = 0.0       # unix ts

    def update(self, equity: float) -> bool:
        """
        Call with current equity on every loop tick.
        Returns True if any halt condition is active (STOP TRADING).
        """
        self._last_equity = equity

        if self.triggered:
            return True

        now_ts = time.time()
        now_dt = datetime.now(timezone.utc)
        today  = now_dt.date()
        day_key  = today.isoformat()
        week_key = f"{today.isocalendar()[0]}-W{today.isocalendar()[1]:02d}"

        # ── Reset daily tracking on new day ──────────────────────────────
        if self._day_key != day_key:
            self._day_key       = day_key
            self._day_start_eq  = equity
            self._daily_halted_until = 0.0

        # ── Reset weekly tracking on new ISO week ─────────────────────────
        if self._week_key != week_key:
            self._week_key       = week_key
            self._week_start_eq  = equity
            self._weekly_halted_until = 0.0

        # ── Active timed halts ────────────────────────────────────────────
        if now_ts < self._daily_halted_until:
            return True
        if now_ts < self._weekly_halted_until:
            return True

        # ── Peak tracking ─────────────────────────────────────────────────
        if equity > self.peak_equity:
            self.peak_equity = equity

        if self.peak_equity <= 0:
            return False

        # ── Tier 1: Trail DD (latching) ───────────────────────────────────
        drawdown = (self.peak_equity - equity) / self.peak_equity
        if drawdown > self.max_drawdown:
            self._trigger_reason = (
                f"Drawdown {drawdown:.2%} exceeded max {self.max_drawdown:.2%}. "
                f"Peak={self.peak_equity:.2f} | Current={equity:.2f}"
            )
            self.triggered = True
            logger.critical(f"[kill_switch] TRIGGERED — {self._trigger_reason}")
            return True

        # ── Tier 2: Daily loss halt ────────────────────────────────────────
        if self._day_start_eq > 0:
            daily_loss = (self._day_start_eq - equity) / self._day_start_eq
            if daily_loss >= settings.MAX_DAILY_LOSS:
                self._daily_halted_until = now_ts + 86400
                logger.warning(
                    f"[kill_switch] Daily halt: {daily_loss:.2%} loss "
                    f"(floor={self._day_start_eq:.2f}) — halted 24h"
                )
                return True

        # ── Tier 3: Weekly loss halt ──────────────────────────────────────
        if self._week_start_eq > 0:
            weekly_loss = (self._week_start_eq - equity) / self._week_start_eq
            if weekly_loss >= WEEKLY_HALT_PCT:
                days_to_monday = (7 - today.weekday()) % 7 or 7
                self._weekly_halted_until = now_ts + days_to_monday * 86400
                logger.warning(
                    f"[kill_switch] Weekly halt: {weekly_loss:.2%} loss "
                    f"(floor={self._week_start_eq:.2f}) — halted {days_to_monday}d"
                )
                return True

        return False

    def reset(self) -> None:
        """Manual reset — only call after reviewing the situation."""
        logger.warning("[kill_switch] Manual reset. Resuming trading.")
        self.triggered           = False
        self.peak_equity         = 0.0
        self._trigger_reason     = ""
        self._daily_halted_until  = 0.0
        self._weekly_halted_until = 0.0

    @property
    def current_drawdown(self) -> float:
        if self.peak_equity <= 0 or self._last_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self._last_equity) / self.peak_equity)

    @property
    def trigger_reason(self) -> str:
        return self._trigger_reason

    def status(self) -> dict:
        now = time.time()
        return {
            "triggered":             self.triggered,
            "peak_equity":           self.peak_equity,
            "max_drawdown_threshold": self.max_drawdown,
            "current_drawdown":      round(self.current_drawdown, 4),
            "reason":                self._trigger_reason,
            "daily_halted":          now < self._daily_halted_until,
            "weekly_halted":         now < self._weekly_halted_until,
        }
