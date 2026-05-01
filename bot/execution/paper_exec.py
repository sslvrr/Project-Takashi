"""
Paper trading broker — full simulation of buy/sell mechanics
without touching real capital. Used as the default MODE=PAPER executor.
"""

import time
from dataclasses import dataclass, field
from typing import Optional
from execution.slippage import apply_slippage
from core.logger import logger


@dataclass
class Position:
    id: str
    symbol: str
    entry: float
    size: float
    tp: float
    sl: float
    direction: str = "BUY"
    strategy: str = "KOTEGAWA"
    score: int = 0
    opened_at: float = field(default_factory=time.time)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.opened_at


class PaperBroker:
    def __init__(self, balance: float = 10_000.0):
        self.balance = balance
        self.initial_balance = balance
        self.positions: list[Position] = []
        self.trade_log: list[dict] = []
        self._id_counter = 0

    # ─── Orders ──────────────────────────────────────────────────────────────

    def buy(
        self,
        symbol: str,
        price: float,
        size: float,
        tp_pct: float = 0.02,
        sl_pct: float = 0.015,
        direction: str = "BUY",
        strategy: str = "KOTEGAWA",
        score: int = 0,
    ) -> Optional[Position]:
        is_long = direction != "SELL"
        fill_price = apply_slippage(price, is_buy=is_long, asset=symbol)
        cost = fill_price * size

        if cost > self.balance:
            logger.warning(f"[paper] INSUFFICIENT FUNDS for {symbol}: need {cost:.2f}, have {self.balance:.2f}")
            return None

        self.balance -= cost
        self._id_counter += 1
        if is_long:
            tp = fill_price * (1 + tp_pct)
            sl = fill_price * (1 - sl_pct)
        else:
            tp = fill_price * (1 - tp_pct)
            sl = fill_price * (1 + sl_pct)
        pos = Position(
            id=f"P{self._id_counter}",
            symbol=symbol,
            entry=fill_price,
            size=size,
            tp=tp,
            sl=sl,
            direction=direction,
            strategy=strategy,
            score=score,
        )
        self.positions.append(pos)
        self.trade_log.append({
            "id": pos.id,
            "action": direction,
            "symbol": symbol,
            "price": fill_price,
            "size": size,
            "balance_after": self.balance,
        })
        logger.info(f"[paper] {direction} {symbol} @ {fill_price:.5f} x{size} | TP={pos.tp:.5f} SL={pos.sl:.5f} | bal={self.balance:.2f}")
        return pos

    def close(self, pos: Position, price: float, reason: str = "manual") -> float:
        is_long = pos.direction != "SELL"
        fill_price = apply_slippage(price, is_buy=not is_long, asset=pos.symbol)
        pnl = ((fill_price - pos.entry) if is_long else (pos.entry - fill_price)) * pos.size
        risk = abs((pos.entry - pos.sl) * pos.size) if pos.sl else None
        r_multiple = round(pnl / risk, 2) if risk else None
        self.balance += pos.size * fill_price
        self.positions.remove(pos)
        self.trade_log.append({
            "id": pos.id,
            "action": "CLOSE",
            "symbol": pos.symbol,
            "entry": pos.entry,
            "exit": fill_price,
            "size": pos.size,
            "pnl": pnl,
            "reason": reason,
            "balance_after": self.balance,
        })
        logger.info(f"[paper] CLOSE {pos.symbol} @ {fill_price:.5f} | PnL={pnl:+.4f} | reason={reason} | bal={self.balance:.2f}")
        return pnl

    # ─── TP/SL sweep ─────────────────────────────────────────────────────────

    def check_exits(self, current_prices: dict[str, float]) -> list[tuple]:
        """
        Sweep all open positions against current prices.
        Returns list of (pos, exit_price, reason, pnl) tuples for closed positions.
        """
        closed = []
        to_close = []

        for pos in self.positions:
            price = current_prices.get(pos.symbol)
            if price is None:
                continue
            if pos.direction == "SELL":
                if price <= pos.tp:
                    to_close.append((pos, price, "TP"))
                elif price >= pos.sl:
                    to_close.append((pos, price, "SL"))
            else:
                if price >= pos.tp:
                    to_close.append((pos, price, "TP"))
                elif price <= pos.sl:
                    to_close.append((pos, price, "SL"))

        for pos, price, reason in to_close:
            pnl = self.close(pos, price, reason)
            closed.append((pos, price, reason, pnl))

        return closed

    # ─── Metrics ─────────────────────────────────────────────────────────────

    @property
    def equity(self) -> float:
        return self.balance

    @property
    def total_pnl(self) -> float:
        return self.balance - self.initial_balance

    @property
    def open_position_count(self) -> int:
        return len(self.positions)

    def get_pnl_series(self) -> list[float]:
        return [t["pnl"] for t in self.trade_log if "pnl" in t]
