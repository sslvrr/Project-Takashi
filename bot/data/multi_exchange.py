"""
Multi-exchange price aggregation (Binance + Kraken).
Used for cross-venue price discrepancy awareness and arbitrage detection.
"""

import asyncio
import ccxt
import ccxt.async_support as ccxt_async
from core.logger import logger


_binance = None
_kraken = None


def _get_binance():
    global _binance
    if _binance is None:
        _binance = ccxt.binance({"enableRateLimit": True})
    return _binance


def _get_kraken():
    global _kraken
    if _kraken is None:
        _kraken = ccxt.kraken({"enableRateLimit": True})
    return _kraken


def get_prices(symbol: str = "XRP/USDT") -> tuple[float, float]:
    """Fetch last price from Binance and Kraken. Returns (binance_price, kraken_price)."""
    try:
        b_ticker = _get_binance().fetch_ticker(symbol)
        b_price = float(b_ticker["last"])
    except Exception as exc:
        logger.warning(f"[multi_exchange] Binance ticker error for {symbol}: {exc}")
        b_price = 0.0

    try:
        # Kraken uses XRP/USDT or XXRPZUSD — map if needed
        k_symbol = "XRP/USDT" if "XRP" in symbol else symbol
        k_ticker = _get_kraken().fetch_ticker(k_symbol)
        k_price = float(k_ticker["last"])
    except Exception as exc:
        logger.warning(f"[multi_exchange] Kraken ticker error for {symbol}: {exc}")
        k_price = 0.0

    return b_price, k_price


def arbitrage_opportunity(
    p1: float, p2: float, threshold: float = 0.002
) -> bool:
    """Return True if price divergence exceeds threshold (0.2% default)."""
    if p1 <= 0 or p2 <= 0:
        return False
    return abs(p1 - p2) / p1 > threshold


def check_arbitrage(symbol: str = "XRP/USDT") -> dict:
    p1, p2 = get_prices(symbol)
    spread_pct = abs(p1 - p2) / p1 * 100 if p1 > 0 else 0
    return {
        "symbol": symbol,
        "binance": p1,
        "kraken": p2,
        "spread_pct": round(spread_pct, 4),
        "opportunity": arbitrage_opportunity(p1, p2),
    }
