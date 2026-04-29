"""
Signal fusion — combines rule-based strategy signal with ML prediction.
Only enters a trade when both layers agree.
"""

from typing import Optional
from core.logger import logger


def final_signal(
    rule_signal: Optional[str],
    ml_prediction: Optional[int],
    ml_proba: float = 0.5,
    confidence_threshold: float = 0.55,
) -> Optional[str]:
    """
    Return the rule signal when both layers agree (or no model is available).
    SELL signals bypass ML (Kotegawa never sells; VENOM uses its own loop).
    """
    if rule_signal not in ("BUY", "SELL"):
        return None

    # SELL signals are directional — ML was trained for BUY only, pass through
    if rule_signal == "SELL":
        return "SELL"

    if ml_prediction is None:
        return rule_signal

    if ml_prediction == 1 and ml_proba >= confidence_threshold:
        logger.debug(f"[fusion] Both layers agree: BUY (proba={ml_proba:.2f})")
        return "BUY"

    logger.debug(f"[fusion] ML vetoed signal (pred={ml_prediction}, proba={ml_proba:.2f} < {confidence_threshold})")
    return None
