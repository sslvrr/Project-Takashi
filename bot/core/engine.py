"""
Async event-driven engine — the main processing pipeline.
Three concurrent coroutines communicate via asyncio queues:
  1. market_data   → strategy_queue
  2. strategy      → execution_queue
  3. execution     → DB + performance tracker
"""

import asyncio
from typing import Optional
import pandas as pd

from core.logger import logger
from core.health import heartbeat
from core.decision import decision_pipeline
from core.performance import record_trade, current_equity
from core.alerts import send_alert
from risk.kill_switch import KillSwitch
from risk.manager import allow_trade, check_daily_loss, check_max_positions
from risk.frequency import FrequencyGuard
from risk.scaling import scale_position
from risk.manager import position_size
from risk.equity_control import equity_filter
from config.settings import settings


class TradingEngine:
    def __init__(
        self,
        broker,               # PaperBroker or live executor
        kill_switch: KillSwitch,
        model=None,
    ):
        self.broker = broker
        self.kill_switch = kill_switch
        self.model = model
        self.frequency_guard = FrequencyGuard(min_interval_seconds=60)
        self.running = True

        # Per-asset state
        self._dfs: dict[str, Optional[pd.DataFrame]] = {}
        self._orderbooks: dict[str, dict] = {}
        self._prev_orderbooks: dict[str, dict] = {}
        self._daily_pnl: float = 0.0

        # Async queues
        self.strategy_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.execution_queue: asyncio.Queue = asyncio.Queue(maxsize=50)

    # ─── Data ingestion ───────────────────────────────────────────────────────

    def update_ohlcv(self, asset: str, df: pd.DataFrame) -> None:
        self._dfs[asset] = df

    def update_orderbook(self, asset: str, ob: dict) -> None:
        self._prev_orderbooks[asset] = self._orderbooks.get(asset, {})
        self._orderbooks[asset] = ob

    # ─── Strategy processing ──────────────────────────────────────────────────

    async def process_strategy(self) -> None:
        """Consume market data events from strategy_queue, generate signals."""
        while self.running:
            try:
                asset = await asyncio.wait_for(self.strategy_queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                continue

            df = self._dfs.get(asset)
            ob = self._orderbooks.get(asset, {})
            prev_ob = self._prev_orderbooks.get(asset, {})

            if df is None or len(df) < 30:
                continue

            # Pre-execution risk checks
            equity = current_equity()
            if self.kill_switch.update(equity):
                logger.critical("[engine] Kill switch active — not executing.")
                send_alert("🔴 KILL SWITCH ACTIVE — System halted.", level="CRITICAL")
                self.running = False
                break

            signal = decision_pipeline(df, ob, prev_ob, asset, self.model)

            try:
                from api.server import push_signal
                push_signal({
                    "asset": asset,
                    "valid": signal is not None and signal.is_valid,
                    "score": getattr(signal, "score", 0) if signal else 0,
                    "price": round(getattr(signal, "price", 0.0) if signal else 0.0, 5),
                    "direction": getattr(signal, "signal", None) if signal else None,
                })
            except Exception:
                pass

            if signal and signal.is_valid:
                await self.execution_queue.put(signal)

            heartbeat()

    # ─── Execution ────────────────────────────────────────────────────────────

    async def process_execution(self) -> None:
        """Consume validated signals and place orders."""
        while self.running:
            try:
                signal = await asyncio.wait_for(self.execution_queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                continue

            asset = signal.asset
            equity = current_equity()

            # All risk gates
            pnl_series = []  # TODO: wire to per-session list
            if not allow_trade(pnl_series):
                logger.warning(f"[engine] Cluster filter blocked {asset} trade.")
                continue
            if not check_daily_loss(self._daily_pnl, equity):
                logger.warning("[engine] Daily loss limit reached — no new trades.")
                continue
            if not check_max_positions(self.broker.open_position_count if hasattr(self.broker, "open_position_count") else 0):
                logger.debug("[engine] Max positions — skipping.")
                continue
            if not self.frequency_guard.can_trade(asset):
                continue

            # Compute size
            raw_sz = position_size(equity, signal.price)
            final_sz = scale_position(raw_sz, equity)

            if final_sz <= 0:
                continue

            # Execute
            if settings.is_paper:
                pos = self.broker.buy(
                    asset, signal.price, final_sz,
                    tp_pct=settings.TAKE_PROFIT_PCT,
                    sl_pct=settings.STOP_LOSS_PCT,
                )
                if pos:
                    self.frequency_guard.record_trade(asset)
                    send_alert(f"🚀 PAPER BUY {asset} @ {signal.price:.5f} | size={final_sz:.4f} | score={signal.score}")
            else:
                logger.info(f"[engine] LIVE order: {asset} size={final_sz}")
                # Live execution wired in execute_live()

    # ─── Main loop ────────────────────────────────────────────────────────────

    async def run(self) -> None:
        logger.info("[engine] Starting async trading engine.")
        await asyncio.gather(
            self.process_strategy(),
            self.process_execution(),
        )
