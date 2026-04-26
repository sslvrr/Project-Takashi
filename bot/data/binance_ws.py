"""
Binance WebSocket — real-time order book + OHLC streaming for XRP/USDT.
Uses @depth@100ms for 100 ms update frequency (near-tick resolution).
"""

import asyncio
import json
from collections import deque
from typing import Callable, Awaitable

import websockets
from websockets.exceptions import ConnectionClosed

from core.logger import logger
from core.retry import async_retry


DEPTH_URL = "wss://stream.binance.com:9443/ws/{symbol}@depth10@100ms"
KLINE_URL = "wss://stream.binance.com:9443/ws/{symbol}@kline_{interval}"
TICKER_URL = "wss://stream.binance.com:9443/ws/{symbol}@ticker"

_latest_orderbook: dict = {}
_latest_ticker: dict = {}
_ohlcv_buffer: deque = deque(maxlen=500)


async def stream_orderbook(
    symbol: str = "xrpusdt",
    callback: Callable[[dict], Awaitable[None]] | None = None,
) -> None:
    """Stream level-2 order book snapshots and call callback on each update."""
    url = DEPTH_URL.format(symbol=symbol.lower())
    logger.info(f"[binance_ws] Connecting order book stream: {url}")

    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                logger.info(f"[binance_ws] Order book stream connected: {symbol.upper()}")
                async for raw in ws:
                    data = json.loads(raw)
                    _latest_orderbook[symbol.upper()] = data
                    if callback:
                        await callback(data)
        except ConnectionClosed as exc:
            logger.warning(f"[binance_ws] Order book stream closed ({exc}). Reconnecting in 3s…")
            await asyncio.sleep(3)
        except Exception as exc:
            logger.error(f"[binance_ws] Order book stream error: {exc}. Reconnecting in 5s…")
            await asyncio.sleep(5)


async def stream_klines(
    symbol: str = "xrpusdt",
    interval: str = "5m",
    callback: Callable[[dict], Awaitable[None]] | None = None,
) -> None:
    """Stream closed kline (OHLCV) data and buffer locally."""
    url = KLINE_URL.format(symbol=symbol.lower(), interval=interval)
    logger.info(f"[binance_ws] Connecting kline stream: {url}")

    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                logger.info(f"[binance_ws] Kline stream connected: {symbol.upper()} {interval}")
                async for raw in ws:
                    data = json.loads(raw)
                    kline = data.get("k", {})
                    if kline.get("x"):  # only closed candles
                        ohlcv = {
                            "time": kline["t"],
                            "open": float(kline["o"]),
                            "high": float(kline["h"]),
                            "low": float(kline["l"]),
                            "close": float(kline["c"]),
                            "volume": float(kline["v"]),
                        }
                        _ohlcv_buffer.append(ohlcv)
                        if callback:
                            await callback(ohlcv)
        except ConnectionClosed as exc:
            logger.warning(f"[binance_ws] Kline stream closed ({exc}). Reconnecting in 3s…")
            await asyncio.sleep(3)
        except Exception as exc:
            logger.error(f"[binance_ws] Kline stream error: {exc}. Reconnecting in 5s…")
            await asyncio.sleep(5)


async def stream_ticker(
    symbol: str = "xrpusdt",
    callback: Callable[[dict], Awaitable[None]] | None = None,
) -> None:
    """Stream 24h ticker for price change / volume context."""
    url = TICKER_URL.format(symbol=symbol.lower())
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                async for raw in ws:
                    data = json.loads(raw)
                    _latest_ticker[symbol.upper()] = data
                    if callback:
                        await callback(data)
        except (ConnectionClosed, Exception) as exc:
            logger.warning(f"[binance_ws] Ticker stream error: {exc}. Reconnecting in 5s…")
            await asyncio.sleep(5)


def get_orderbook(symbol: str = "XRP") -> dict:
    """Return latest cached order book snapshot."""
    return _latest_orderbook.get(symbol, {})


def get_ohlcv_buffer() -> list[dict]:
    """Return list of recent closed candles."""
    return list(_ohlcv_buffer)


def get_ticker(symbol: str = "XRP") -> dict:
    """Return latest cached ticker."""
    return _latest_ticker.get(symbol, {})
