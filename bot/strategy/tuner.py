"""
Parameter auto-tuner — random search over strategy parameter space.
Runs offline against historical feature store data.
"""

import random
from core.logger import logger


def random_search(
    params: dict[str, list],
    score_fn,
    iterations: int = 30,
) -> tuple[dict, float]:
    """
    Simple random search over parameter grid.
    params: {param_name: [candidate_values]}
    score_fn: callable(params_dict) -> float
    Returns (best_params, best_score)
    """
    best_params = None
    best_score = float("-inf")

    for i in range(iterations):
        trial = {k: random.choice(v) for k, v in params.items()}
        try:
            score = score_fn(trial)
        except Exception as exc:
            logger.debug(f"[tuner] Trial {i} failed: {exc}")
            continue

        if score > best_score:
            best_score = score
            best_params = trial

    logger.info(f"[tuner] Best score={best_score:.4f} | params={best_params}")
    return best_params or {}, best_score


PARAM_SPACE = {
    "panic_drop_threshold": [-0.02, -0.03, -0.04, -0.05],
    "rsi_oversold": [25, 27, 30, 32],
    "ob_imbalance_threshold": [0.55, 0.58, 0.60, 0.62, 0.65],
    "take_profit_pct": [0.01, 0.015, 0.02, 0.025, 0.03],
    "stop_loss_pct": [0.01, 0.015, 0.02],
}
