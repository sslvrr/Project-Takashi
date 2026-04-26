"""
Real-time performance tracker — records trade PnL and computes live metrics.
Shared singleton used by the main loop, API, and dashboard.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class PerformanceTracker:
    trades: list[float] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    _start_equity: float = 10_000.0

    def record(self, pnl: float) -> None:
        self.trades.append(pnl)
        current = (self.equity_curve[-1] if self.equity_curve else self._start_equity) + pnl
        self.equity_curve.append(current)

    def metrics(self) -> dict:
        if not self.trades:
            return {
                "pnl": 0.0,
                "trades": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "equity": self._start_equity,
            }
        wins = [t for t in self.trades if t > 0]
        losses = [t for t in self.trades if t < 0]
        pf = (sum(wins) / abs(sum(losses))) if losses else 0.0
        return {
            "pnl": round(sum(self.trades), 4),
            "trades": len(self.trades),
            "win_rate": round(len(wins) / len(self.trades), 4),
            "avg_win": round(sum(wins) / len(wins), 6) if wins else 0.0,
            "avg_loss": round(sum(losses) / len(losses), 6) if losses else 0.0,
            "profit_factor": round(pf, 4),
            "equity": round(self.equity_curve[-1] if self.equity_curve else self._start_equity, 2),
        }

    @property
    def total_pnl(self) -> float:
        return sum(self.trades)

    @property
    def current_equity(self) -> float:
        return self.equity_curve[-1] if self.equity_curve else self._start_equity


# Module-level singleton
_tracker = PerformanceTracker()


def record_trade(pnl: float) -> None:
    _tracker.record(pnl)


def get_metrics() -> dict:
    return _tracker.metrics()


def get_equity_curve() -> list[float]:
    return _tracker.equity_curve


def get_pnl_series() -> list[float]:
    return _tracker.trades


def current_equity() -> float:
    return _tracker.current_equity
