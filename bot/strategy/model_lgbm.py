"""
LightGBM ML model — short-term directional prediction.
Predicts whether next bar's close will be higher (1) or lower/flat (0).
"""

import os
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional

from core.logger import logger

_MODEL_PATH = Path(__file__).parent.parent / "models" / "lgbm_model.pkl"
_MODEL_PATH.parent.mkdir(exist_ok=True)

try:
    import lightgbm as lgb
    _LGB_AVAILABLE = True
except ImportError:
    _LGB_AVAILABLE = False
    logger.warning("[model_lgbm] LightGBM not installed. ML layer disabled.")


class LGBMModel:
    def __init__(self):
        self.model = None
        self._trained = False

    def _build(self):
        if not _LGB_AVAILABLE:
            return None
        return lgb.LGBMClassifier(
            n_estimators=200,
            learning_rate=0.05,
            max_depth=6,
            num_leaves=31,
            min_child_samples=20,
            subsample=0.8,
            colsample_bytree=0.8,
            class_weight="balanced",
            n_jobs=-1,
            verbose=-1,
        )

    def train(self, X: pd.DataFrame, y: pd.Series) -> bool:
        if not _LGB_AVAILABLE or len(X) < 50:
            return False
        try:
            self.model = self._build()
            self.model.fit(X.values, y.values)
            self._trained = True
            logger.info(f"[model_lgbm] Trained on {len(X)} samples.")
            return True
        except Exception as exc:
            logger.error(f"[model_lgbm] Training error: {exc}")
            return False

    def predict(self, features: dict) -> int:
        """Return 1 (bullish) or 0 (bearish/flat). Returns 0 if model not trained."""
        if not self._trained or self.model is None:
            return 0
        try:
            arr = np.array(list(features.values()), dtype=float).reshape(1, -1)
            return int(self.model.predict(arr)[0])
        except Exception as exc:
            logger.debug(f"[model_lgbm] Predict error: {exc}")
            return 0

    def predict_proba(self, features: dict) -> float:
        """Return probability of upward move."""
        if not self._trained or self.model is None:
            return 0.5
        try:
            arr = np.array(list(features.values()), dtype=float).reshape(1, -1)
            proba = self.model.predict_proba(arr)[0]
            return float(proba[1])
        except Exception:
            return 0.5

    def save(self) -> None:
        if self.model and self._trained:
            joblib.dump(self.model, _MODEL_PATH)
            logger.info(f"[model_lgbm] Model saved to {_MODEL_PATH}")

    def load(self) -> bool:
        if not _LGB_AVAILABLE or not _MODEL_PATH.exists():
            return False
        try:
            self.model = joblib.load(_MODEL_PATH)
            self._trained = True
            logger.info(f"[model_lgbm] Model loaded from {_MODEL_PATH}")
            return True
        except Exception as exc:
            logger.error(f"[model_lgbm] Load error: {exc}")
            return False

    def feature_importance(self, feature_names: list[str]) -> dict:
        if not self._trained or self.model is None:
            return {}
        importances = self.model.feature_importances_
        return dict(sorted(
            zip(feature_names, importances),
            key=lambda x: x[1],
            reverse=True,
        ))

    @property
    def is_trained(self) -> bool:
        return self._trained
