"""
Unified decision pipeline — the brain of the system.
Combines rule-based signal + ML prediction into one final trade decision.
"""

from typing import Optional
import pandas as pd

from strategy.core import Signal, generate_signal
from strategy.features import build_features
from strategy.filter import signal_filter
from strategy.orderflow import orderflow_score
from core.logger import logger


def decision_pipeline(
    df: pd.DataFrame,
    orderbook: dict,
    prev_ob: Optional[dict],
    asset: str,
    model=None,   # Optional LGBMModel / MLModel instance
) -> Optional[Signal]:
    """
    Full decision pipeline:
    1. Build features
    2. Get ML prediction (if model available)
    3. Generate Kotegawa rule signal
    4. Apply signal filter
    5. Return Signal if all layers agree
    """
    features = build_features(df, orderbook)
    ml_pred = None

    if model is not None and features is not None:
        try:
            ml_pred = int(model.predict(features))
        except Exception as exc:
            logger.debug(f"[decision] ML predict error for {asset}: {exc}")

    signal = generate_signal(
        df=df,
        orderbook=orderbook,
        prev_ob=prev_ob,
        asset=asset,
        ml_prediction=ml_pred,
    )

    if signal is None:
        return None

    # Apply market quality filter
    vol = float(df["close"].pct_change().rolling(20).std().iloc[-1]) if len(df) >= 20 else 0.002
    if not signal_filter(signal.score, vol, signal.spread, asset):
        return None

    return signal
