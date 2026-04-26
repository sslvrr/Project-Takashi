from typing import Optional
"""
Slippage and spread model — used in both paper and live execution
to compute realistic fill prices and decide limit vs market entry.
"""

from strategy.orderflow import get_spread


# Typical Binance XRPUSDT spread: ~0.0001
# Typical EURUSD spread at broker: ~0.0001–0.0002
CRYPTO_SLIPPAGE = 0.0001
FX_SLIPPAGE = 0.0002


def apply_slippage(
    price: float,
    is_buy: bool = True,
    asset: str = "XRP",
    spread: Optional[float] = None,
) -> float:
    """
    Return realistic fill price including spread and slippage.
    Buys pay slightly more; sells receive slightly less.
    """
    slip = FX_SLIPPAGE if "USD" in asset and len(asset) > 3 else CRYPTO_SLIPPAGE
    sp = spread if spread is not None else slip
    adj = sp + slip
    return price + adj if is_buy else price - adj


def smart_entry_price(orderbook: dict) -> tuple[str, float]:
    """
    Return (order_type, price) for smart entry.
    Narrow spread → use limit at best bid.
    Wide spread   → use market at best ask.
    """
    bids = orderbook.get("bids", []) or orderbook.get("b", [])
    asks = orderbook.get("asks", []) or orderbook.get("a", [])

    if not bids or not asks:
        return ("MARKET", 0.0)

    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])
    spread = best_ask - best_bid

    if spread < 0.0005:
        return ("LIMIT", best_bid)
    return ("MARKET", best_ask)


def max_acceptable_spread(asset: str) -> float:
    """Return the maximum spread we're willing to trade at."""
    if "USD" in asset and len(asset) > 3:
        return 0.0002      # EURUSD ~2 pips max
    return 0.005           # Crypto 0.5% max
