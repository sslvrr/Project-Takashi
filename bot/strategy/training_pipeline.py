"""
Automated retraining pipeline — pulls from feature store,
trains the LightGBM model, and persists the result.
Designed to run daily or every N trades.
"""

from db.feature_store import FeatureStore
from strategy.model_lgbm import LGBMModel
from strategy.features import FEATURE_NAMES
from core.logger import logger


def run_training(
    feature_store: FeatureStore,
    model: LGBMModel,
    min_samples: int = 100,
) -> bool:
    """
    Retrain model from feature store if sufficient data is available.
    Returns True on successful retraining.
    """
    X, y = feature_store.get_training_data(min_samples=min_samples)

    if X.empty:
        logger.info(f"[training] Insufficient data ({feature_store.size()} samples < {min_samples}). Skipping.")
        return False

    # Align features to expected columns
    for col in FEATURE_NAMES:
        if col not in X.columns:
            X[col] = 0.0
    X = X[FEATURE_NAMES]

    success = model.train(X, y)
    if success:
        model.save()
        imp = model.feature_importance(FEATURE_NAMES)
        top = sorted(imp.items(), key=lambda x: x[1], reverse=True)[:3]
        logger.info(f"[training] Top features: {top}")
    return success


def build_target(df, lookahead: int = 1) -> int:
    """
    Return 1 if price rises over next `lookahead` bar(s), else 0.
    Used when labelling feature snapshots.
    """
    if len(df) < lookahead + 1:
        return 0
    current = float(df["close"].iloc[-1])
    future = float(df["close"].iloc[-1 + lookahead]) if len(df) > lookahead else current
    return 1 if future > current else 0
