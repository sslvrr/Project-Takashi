"""
Coinbase Advanced Trade WebSocket — real-time order book + candle streaming for XRP/USD.
Public channels (level2, candles, ticker) require no API keys.
"""

import asyncio
import json
from collections import deque
from typing import Optional, Callable, Awaitable

import websockets
from websockets.exceptions import ConnectionClosed

from core.logger import logger


WS_URL = "wss://advanced-trade-ws.coinbase.com"

_latest_orderbook: dict = {}
_latest_ticker: dict = {}
_ohlcv_buffer: deque = deque(maxlen=500)

# Local order book state for incremental level2 reconstruction
_bids: dict = {}
_asks: dict = {}


async def stream_orderbook(
    symbol: str = "XRP-USD",
    callback: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> None:
    """Stream level-2 order book snapshots and call callback on each update."""
    logger.info(f"[coinbase_ws] Connecting order book stream for {symbol}")
    asset = symbol.split("-")[0]

    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=10, max_size=10_000_000) as ws:
                await ws.send(json.dumps({
                    "type": "subscribe",
                    "product_ids": [symbol],
                    "channel": "level2",
                }))
                logger.info(f"[coinbase_ws] Order book stream connected: {symbol}")

                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("channel") != "l2_data":
                        continue

                    for event in msg.get("events", []):
                        if event.get("type") == "snapshot":
                            _bids.clear()
                            _asks.clear()

                        for u in event.get("updates", []):
                            price = float(u["price_level"])
                            qty = float(u["new_quantity"])
                            if u["side"] == "bid":
                                if qty == 0:
                                    _bids.pop(price, None)
                                else:
                                    _bids[price] = qty
                            else:
                                if qty == 0:
                                    _asks.pop(price, None)
                                else:
                                    _asks[price] = qty

                        book = {
                            "bids": sorted([[p, s] for p, s in _bids.items()], reverse=True)[:10],
                            "asks": sorted([[p, s] for p, s in _asks.items()])[:10],
                        }
                        _latest_orderbook[asset] = book
                        if callback:
                            await callback(book)

        except ConnectionClosed as exc:
            logger.warning(f"[coinbase_ws] Order book stream closed ({exc}). Reconnecting in 3s…")
            await asyncio.sleep(3)
        except Exception as exc:
            logger.error(f"[coinbase_ws] Order book stream error: {exc}. Reconnecting in 5s…")
            await asyncio.sleep(5)


async def stream_klines(
    symbol: str = "XRP-USD",
    interval: str = "5m",
    callback: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> None:
    """Stream closed candle (OHLCV) data and buffer locally."""
    logger.info(f"[coinbase_ws] Connecting candles stream for {symbol}")

    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=10) as ws:
                await ws.send(json.dumps({
                    "type": "subscribe",
                    "product_ids": [symbol],
                    "channel": "candles",
                }))
                logger.info(f"[coinbase_ws] Candles stream connected: {symbol}")
                seen_starts: set = set()

                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("channel") != "candles":
                        continue

                    for event in msg.get("events", []):
                        for candle in event.get("candles", []):
                            start = int(candle["start"])
                            if start in seen_starts:
                                continue
                            seen_starts.add(start)

                            ohlcv = {
                                "time": start * 1000,
                                "open": float(candle["open"]),
                                "high": float(candle["high"]),
                                "low": float(candle["low"]),
                                "close": float(candle["close"]),
                                "volume": float(candle["volume"]),
                            }
                            _ohlcv_buffer.append(ohlcv)
                            if callback:
                                await callback(ohlcv)

        except ConnectionClosed as exc:
            logger.warning(f"[coinbase_ws] Candles stream closed ({exc}). Reconnecting in 3s…")
            await asyncio.sleep(3)
        except Exception as exc:
            logger.error(f"[coinbase_ws] Candles stream error: {exc}. Reconnecting in 5s…")
            await asyncio.sleep(5)


async def stream_ticker(
    symbol: str = "XRP-USD",
    callback: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> None:
    """Stream ticker for real-time price context."""
    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=10) as ws:
                await ws.send(json.dumps({
                    "type": "subscribe",
                    "product_ids": [symbol],
                    "channel": "ticker",
                }))
                asset = symbol.split("-")[0]
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("channel") != "ticker":
                        continue
                    for event in msg.get("events", []):
                        for tick in event.get("tickers", []):
                            _latest_ticker[asset] = tick
                            if callback:
                                await callback(tick)
        except (ConnectionClosed, Exception) as exc:
            logger.warning(f"[coinbase_ws] Ticker stream error: {exc}. Reconnecting in 5s…")
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
