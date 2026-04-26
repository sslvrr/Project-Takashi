"""
Multi-exchange price aggregation (Coinbase + Kraken).
Used for cross-venue price discrepancy awareness and arbitrage detection.
"""

import ccxt
from core.logger import logger


_coinbase = None
_kraken = None


def _get_coinbase():
    global _coinbase
    if _coinbase is None:
        _coinbase = ccxt.coinbase({"enableRateLimit": True})
    return _coinbase


def _get_kraken():
    global _kraken
    if _kraken is None:
        _kraken = ccxt.kraken({"enableRateLimit": True})
    return _kraken


def get_prices(symbol: str = "XRP/USD") -> tuple[float, float]:
    """Fetch last price from Coinbase and Kraken. Returns (coinbase_price, kraken_price)."""
    try:
        c_ticker = _get_coinbase().fetch_ticker(symbol)
        c_price = float(c_ticker["last"])
    except Exception as exc:
        logger.warning(f"[multi_exchange] Coinbase ticker error for {symbol}: {exc}")
        c_price = 0.0

    try:
        k_ticker = _get_kraken().fetch_ticker(symbol)
        k_price = float(k_ticker["last"])
    except Exception as exc:
        logger.warning(f"[multi_exchange] Kraken ticker error for {symbol}: {exc}")
        k_price = 0.0

    return c_price, k_price


def arbitrage_opportunity(
    p1: float, p2: float, threshold: float = 0.002
) -> bool:
    """Return True if price divergence exceeds threshold (0.2% default)."""
    if p1 <= 0 or p2 <= 0:
        return False
    return abs(p1 - p2) / p1 > threshold


def check_arbitrage(symbol: str = "XRP/USD") -> dict:
    p1, p2 = get_prices(symbol)
    spread_pct = abs(p1 - p2) / p1 * 100 if p1 > 0 else 0
    return {
        "symbol": symbol,
        "coinbase": p1,
        "kraken": p2,
        "spread_pct": round(spread_pct, 4),
        "opportunity": arbitrage_opportunity(p1, p2),
    }
