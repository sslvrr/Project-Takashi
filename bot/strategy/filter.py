"""
Signal quality filter — prevents trading in bad market conditions.
Acts as a final gate before order execution.
"""

from config.settings import settings
from core.logger import logger


def signal_filter(
    score: int,
    volatility: float,
    spread: float,
    asset: str = "",
) -> bool:
    """
    Return True only when market conditions warrant trading.
    - score: Kotegawa composite score
    - volatility: recent price std dev (as fraction, e.g. 0.003)
    - spread: bid/ask spread (same units as price)
    """
    if score < settings.MIN_SIGNAL_SCORE:
        logger.debug(f"[filter] {asset} rejected: score {score} < {settings.MIN_SIGNAL_SCORE}")
        return False

    if volatility < 0.001:
        logger.debug(f"[filter] {asset} rejected: dead market (vol={volatility:.4f})")
        return False

    max_spread = 0.005 if "USD" in asset else 0.003
    if spread > max_spread:
        logger.debug(f"[filter] {asset} rejected: spread {spread:.5f} > {max_spread}")
        return False

    return True
