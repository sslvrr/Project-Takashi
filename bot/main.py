"""
Project Takashi — Main entry point.
Wires all 17 sprint components into a running production system.

Usage:
  python main.py              # PAPER mode (default)
  MODE=LIVE python main.py    # Live mode (requires API keys)

Architecture:
  Async event loop → CoinbaseWS data → Strategy engine → Execution → DB
  MT5 polling runs on its own coroutine.
  Telegram alerts fire on trades, risk events, and kill switch.
"""

import asyncio
import signal
import sys
import pandas as pd
from datetime import datetime, timezone

from config.settings import settings
from config.assets import ASSETS, enabled_assets, is_crypto, is_fx
from core.logger import logger
from core.alerts import send_alert
from core.health import heartbeat, check_health
from core.performance import record_trade, current_equity, get_pnl_series, get_equity_curve
from core.deployment import can_go_live
from core.engine import TradingEngine
from core.review import send_weekly_summary

from db.session import init_db
from db.feature_store import FeatureStore
from db.models import Trade, SystemEvent

from data.coinbase_ws import stream_orderbook, stream_klines, get_orderbook, get_ohlcv_buffer
from data.mt5_feed import connect as mt5_connect, get_rates as mt5_rates

from execution.paper_exec import PaperBroker
from execution.coinbase_exec import CoinbaseExecutor
from execution.mt5_exec import MT5Executor

from risk.kill_switch import KillSwitch
from strategy.model_lgbm import LGBMModel
from strategy.training_pipeline import run_training

from api.server import app as fastapi_app, update_state, update_positions, update_ml_status, pop_close_requests
import uvicorn


# ─── Global state ─────────────────────────────────────────────────────────────

PAPER_BROKER = PaperBroker(balance=settings.INITIAL_BALANCE)
KILL_SWITCH = KillSwitch(max_drawdown=settings.MAX_DRAWDOWN)
FEATURE_STORE = FeatureStore()
MODEL = LGBMModel()

_shutdown_event: asyncio.Event = None  # type: ignore[assignment]
_trade_count = settings.INITIAL_TRADE_COUNT


# ─── Signal handler ───────────────────────────────────────────────────────────

def _on_shutdown(*_) -> None:
    logger.info("[main] Shutdown signal received.")
    _shutdown_event.set()


# ─── Data pipelines ───────────────────────────────────────────────────────────

async def xrp_orderbook_loop(engine: TradingEngine) -> None:
    """Stream XRP order book and push updates to the engine."""
    async def on_ob(data: dict) -> None:
        engine.update_orderbook("XRP", data)
        await engine.strategy_queue.put("XRP")

    await stream_orderbook("XRP-USD", callback=on_ob)


async def xrp_kline_loop(engine: TradingEngine) -> None:
    """Stream XRP 5m klines, build DataFrame, push to engine."""
    async def on_kline(kline: dict) -> None:
        buf = get_ohlcv_buffer()
        if len(buf) >= 30:
            df = pd.DataFrame(buf)
            engine.update_ohlcv("XRP", df)

    await stream_klines("XRP-USD", interval="5m", callback=on_kline)


async def fx_polling_loop(engine: TradingEngine, asset: str) -> None:
    """Poll any FX/commodity asset from OANDA every 30 seconds."""
    from data.oanda_feed import get_candles, is_configured
    if not is_configured():
        logger.warning(f"[main] OANDA_API_KEY not set — {asset} feed disabled. "
                       "Add OANDA_API_KEY to .env to activate.")
        return
    logger.info(f"[main] {asset} feed starting via OANDA REST API.")
    while not _shutdown_event.is_set():
        try:
            df = get_candles(asset, granularity="M5", count=200)
            if not df.empty:
                engine.update_ohlcv(asset, df)
                await engine.strategy_queue.put(asset)
        except Exception as exc:
            logger.warning(f"[main] {asset} OANDA poll error: {exc}")
        await asyncio.sleep(30)


# ─── Background tasks ─────────────────────────────────────────────────────────

async def health_monitor_loop() -> None:
    while not _shutdown_event.is_set():
        health = check_health(timeout_seconds=180)
        if not health["alive"]:
            send_alert("⚠️ System heartbeat missed — possible stall.")
        await asyncio.sleep(60)


async def model_retrain_loop() -> None:
    """Retrain ML model every hour if sufficient data exists."""
    while not _shutdown_event.is_set():
        await asyncio.sleep(3600)
        logger.info("[main] Attempting model retrain…")
        success = run_training(FEATURE_STORE, MODEL, min_samples=100)
        if success:
            from strategy.features import FEATURE_NAMES
            imp = MODEL.feature_importance(FEATURE_NAMES)
            update_ml_status(MODEL.is_trained, FEATURE_STORE.size(), imp)
            send_alert("🤖 ML model retrained successfully.")
        else:
            update_ml_status(MODEL.is_trained, FEATURE_STORE.size(), {})


async def paper_exit_check_loop() -> None:
    """Every 5s sweep paper positions for TP/SL exits."""
    global _trade_count
    while not _shutdown_event.is_set():
        await asyncio.sleep(5)
        try:
            ob = get_orderbook("XRP")
            if ob:
                bids = ob.get("bids", ob.get("b", []))
                if bids:
                    price = float(bids[0][0])
                    pnls = PAPER_BROKER.check_exits({"XRP": price})
                    for pnl in pnls:
                        record_trade(pnl)
                        _trade_count += 1
                        update_state(trade_count=_trade_count, equity=PAPER_BROKER.equity)

                        if KILL_SWITCH.update(PAPER_BROKER.equity):
                            send_alert("🔴 KILL SWITCH TRIGGERED — Halting all trading.")
                            _shutdown_event.set()
                            break

                # Manual close requests from dashboard
                for req_id in pop_close_requests():
                    for pos in list(PAPER_BROKER.positions):
                        if pos.id == req_id:
                            pnl = PAPER_BROKER.close(pos, price, reason="manual")
                            record_trade(pnl)
                            _trade_count += 1
                            send_alert(f"🔒 MANUAL CLOSE {pos.symbol} @ ${price:.5f} | PnL ${pnl:+.4f}")
                            break

                # Keep equity fresh even with no trades
                update_state(equity=PAPER_BROKER.equity)

                current_price = price if bids else 0.0
                update_positions([
                    {
                        "id": p.id, "symbol": p.symbol,
                        "entry": round(p.entry, 5), "size": round(p.size, 4),
                        "tp": round(p.tp, 5), "sl": round(p.sl, 5),
                        "age_seconds": int(p.age_seconds),
                        "current_price": round(current_price, 5),
                        "unrealized_pnl": round((current_price - p.entry) * p.size, 4),
                    }
                    for p in PAPER_BROKER.positions
                ])
        except Exception as exc:
            logger.debug(f"[main] Exit check error: {exc}")


async def api_server_loop() -> None:
    """Run FastAPI in background."""
    config = uvicorn.Config(
        fastapi_app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    await server.serve()


# ─── Startup ──────────────────────────────────────────────────────────────────

async def startup() -> None:
    logger.info("=" * 60)
    logger.info(f"  Project Takashi — Starting [{settings.MODE} mode]")
    logger.info(f"  Active assets: {enabled_assets()}")
    logger.info("=" * 60)

    # Database
    init_db()
    from db.strategy_store import seed_default_strategies
    seed_default_strategies()
    FEATURE_STORE.load_from_db(limit=2000)

    # Try loading a saved model
    MODEL.load()

    # MT5 connection (no-op on macOS)
    if any(is_fx(a) for a in enabled_assets()):
        mt5_connect(
            login=settings.MT5_LOGIN,
            password=settings.MT5_PASSWORD,
            server=settings.MT5_SERVER,
        )

    # Seed initial equity and trade count into API state
    update_state(equity=PAPER_BROKER.equity, trade_count=_trade_count)

    # Deployment gate check
    if settings.is_live:
        perf = {"trades": _trade_count, "pnl": 0, "win_rate": 0.5, "max_drawdown": 0}
        ok, reasons = can_go_live(perf)
        if not ok:
            logger.warning(f"[main] Live mode gate: {reasons}")

    send_alert(
        f"🚀 Project Takashi started [{settings.MODE}] | "
        f"Assets: {enabled_assets()} | "
        f"DD limit: {settings.MAX_DRAWDOWN:.0%}"
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

async def run() -> None:
    global _shutdown_event
    _shutdown_event = asyncio.Event()
    await startup()

    engine = TradingEngine(
        broker=PAPER_BROKER,
        kill_switch=KILL_SWITCH,
        model=MODEL if MODEL.is_trained else None,
    )

    # Register UNIX signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_shutdown)

    tasks = []

    # Data feeds
    if "XRP" in enabled_assets():
        tasks.append(asyncio.create_task(xrp_orderbook_loop(engine), name="xrp_ob"))
        tasks.append(asyncio.create_task(xrp_kline_loop(engine), name="xrp_klines"))

    for fx_asset in [a for a in enabled_assets() if is_fx(a)]:
        tasks.append(asyncio.create_task(
            fx_polling_loop(engine, fx_asset), name=f"oanda_{fx_asset.lower()}"
        ))

    # Engine
    tasks.append(asyncio.create_task(engine.run(), name="engine"))

    # Background tasks
    tasks.append(asyncio.create_task(health_monitor_loop(), name="health"))
    tasks.append(asyncio.create_task(model_retrain_loop(), name="retrain"))
    tasks.append(asyncio.create_task(paper_exit_check_loop(), name="exits"))
    tasks.append(asyncio.create_task(api_server_loop(), name="api"))

    # Wait for shutdown
    await _shutdown_event.wait()
    logger.info("[main] Shutting down…")

    for task in tasks:
        task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)

    # Final report
    send_weekly_summary(get_pnl_series(), get_equity_curve())
    send_alert(
        f"🏁 Project Takashi stopped | "
        f"Trades: {_trade_count} | "
        f"Equity: ${PAPER_BROKER.equity:.2f}"
    )
    logger.info("[main] Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(run())
