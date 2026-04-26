"""
Live Coinbase Advanced Trade execution engine (XRP/USD).
Only activated when MODE=LIVE and API keys are configured.
Uses limit orders by default; falls back to market on wide spread.
"""

import os
from typing import Optional

import ccxt

from execution.slippage import smart_entry_price, max_acceptable_spread
from core.logger import logger


def _make_exchange(api_key: str = "", secret: str = "") -> ccxt.coinbase:
    return ccxt.coinbase({
        "apiKey": api_key or os.getenv("COINBASE_API_KEY", ""),
        "secret": secret or os.getenv("COINBASE_SECRET", ""),
        "enableRateLimit": True,
    })


class CoinbaseExecutor:
    def __init__(self):
        self._exchange = _make_exchange()

    def place_order(
        self,
        symbol: str,
        size: float,
        orderbook: Optional[dict] = None,
        tp_pct: float = 0.02,
        sl_pct: float = 0.015,
    ) -> dict:
        """
        Place a live buy order on Coinbase Advanced Trade.
        Uses smart entry (limit if spread is tight, market otherwise).
        Returns the exchange order dict.
        """
        order_type, price = smart_entry_price(orderbook or {})

        max_sp = max_acceptable_spread(symbol)
        from strategy.orderflow import get_spread
        real_spread = get_spread(orderbook or {})
        if real_spread > max_sp:
            logger.warning(f"[coinbase_exec] Spread {real_spread:.5f} > max {max_sp} for {symbol}. Skipping.")
            return {}

        try:
            if order_type == "LIMIT" and price > 0:
                order = self._exchange.create_limit_buy_order(symbol, size, price)
            else:
                order = self._exchange.create_market_buy_order(symbol, size)

            logger.info(f"[coinbase_exec] ORDER PLACED: {symbol} {order_type} {size} @ {price} → id={order.get('id')}")
            return order
        except ccxt.BaseError as exc:
            logger.error(f"[coinbase_exec] Order failed for {symbol}: {exc}")
            return {}

    def close_position(self, symbol: str, size: float) -> dict:
        """Market sell to exit position."""
        try:
            order = self._exchange.create_market_sell_order(symbol, size)
            logger.info(f"[coinbase_exec] CLOSE {symbol} size={size} → id={order.get('id')}")
            return order
        except ccxt.BaseError as exc:
            logger.error(f"[coinbase_exec] Close failed for {symbol}: {exc}")
            return {}

    def get_balance(self, asset: str = "USD") -> float:
        try:
            bal = self._exchange.fetch_balance()
            return float(bal["total"].get(asset, 0))
        except Exception as exc:
            logger.error(f"[coinbase_exec] Balance fetch error: {exc}")
            return 0.0

    def get_open_orders(self, symbol: str) -> list[dict]:
        try:
            return self._exchange.fetch_open_orders(symbol)
        except Exception as exc:
            logger.error(f"[coinbase_exec] Open orders fetch error: {exc}")
            return []


def split_order(size: float, parts: int = 3) -> list[float]:
    """Split a total order size into N equal chunks (scale-in)."""
    chunk = size / parts
    return [chunk] * parts
