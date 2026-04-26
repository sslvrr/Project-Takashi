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
    Return "BUY" only when:
    - Rule engine says BUY
    - ML model predicts 1 (or no model available — pass-through)
    - ML probability exceeds confidence_threshold
    """
    if rule_signal != "BUY":
        return None

    if ml_prediction is None:
        # No model — allow rule signal through
        return rule_signal

    if ml_prediction == 1 and ml_proba >= confidence_threshold:
        logger.debug(f"[fusion] Both layers agree: BUY (proba={ml_proba:.2f})")
        return "BUY"

    logger.debug(f"[fusion] ML vetoed signal (pred={ml_prediction}, proba={ml_proba:.2f} < {confidence_threshold})")
    return None
