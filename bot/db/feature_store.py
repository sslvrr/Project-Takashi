"""
Feature store — centralised storage and retrieval of ML training data.
Persists to PostgreSQL via FeatureSnapshot; also maintains an in-memory
deque for fast access during live training loops.
"""

from collections import deque
from datetime import datetime, timezone
from typing import Optional
import pandas as pd

from db.models import FeatureSnapshot
from db.session import get_session
from core.logger import logger

_MAX_MEMORY = 10_000


class FeatureStore:
    def __init__(self):
        self._memory: deque[dict] = deque(maxlen=_MAX_MEMORY)

    def add(self, features: dict, symbol: str = "", target: Optional[int] = None) -> None:
        """Add a feature vector to the in-memory store and persist to DB."""
        record = {**features, "symbol": symbol, "target": target}
        self._memory.append(record)

        # Async-friendly: persist to DB if available
        with get_session() as session:
            if session is None:
                return
            try:
                row = FeatureSnapshot(
                    symbol=symbol,
                    features=features,
                    target=target,
                )
                session.add(row)
            except Exception as exc:
                logger.debug(f"[feature_store] DB persist error: {exc}")

    def get_training_data(self, min_samples: int = 100) -> tuple[pd.DataFrame, pd.Series]:
        """
        Return (X, y) for model training.
        Filters out rows with null target.
        """
        rows = [r for r in self._memory if r.get("target") is not None]
        if len(rows) < min_samples:
            return pd.DataFrame(), pd.Series(dtype=int)

        df = pd.DataFrame(rows)
        y = df.pop("target").astype(int)

        # Drop metadata columns not used as features
        for col in ["symbol", "recorded_at"]:
            if col in df.columns:
                df.drop(columns=[col], inplace=True)

        df = df.select_dtypes(include="number").fillna(0)
        return df, y

    def size(self) -> int:
        return len(self._memory)

    def load_from_db(self, symbol: str = "", limit: int = 5000) -> None:
        """Reload historical snapshots from PostgreSQL into memory."""
        with get_session() as session:
            if session is None:
                return
            query = session.query(FeatureSnapshot)
            if symbol:
                query = query.filter(FeatureSnapshot.symbol == symbol)
            rows = query.order_by(FeatureSnapshot.id.desc()).limit(limit).all()

        for row in reversed(rows):
            record = {**row.features, "symbol": row.symbol, "target": row.target}
            self._memory.append(record)

        logger.info(f"[feature_store] Loaded {len(rows)} rows from DB.")
