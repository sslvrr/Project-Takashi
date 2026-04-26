"""
Feature engineering for the ML layer.
Combines price action + order flow into a flat feature vector.
"""

import numpy as np
import pandas as pd
from typing import Optional

from strategy.indicators import (
    compute_rsi,
    compute_ma,
    compute_vwap,
    compute_atr,
)
from strategy.orderflow import imbalance, get_spread, get_mid_price
from core.logger import logger


def build_features(df: pd.DataFrame, orderbook: dict) -> Optional[dict]:
    """
    Build a flat feature dict from the most recent bar + live order book.
    Returns None if insufficient data.
    """
    if df is None or len(df) < 26:
        return None

    try:
        close = df["close"]
        volume = df["volume"]

        rsi = compute_rsi(close).iloc[-1]
        ma25 = compute_ma(close, 25).iloc[-1]
        vwap = compute_vwap(df).iloc[-1]
        atr = compute_atr(df).iloc[-1]

        price = float(close.iloc[-1])
        prev_price = float(close.iloc[-2])
        ret = (price - prev_price) / prev_price if prev_price != 0 else 0

        vol_20_avg = float(volume.rolling(20).mean().iloc[-1])
        vol_ratio = float(volume.iloc[-1]) / vol_20_avg if vol_20_avg > 0 else 1.0

        volatility = float(close.pct_change().rolling(20).std().iloc[-1])

        ma25_dev = (price - float(ma25)) / float(ma25) if ma25 != 0 else 0
        vwap_dev = (price - float(vwap)) / float(vwap) if vwap != 0 else 0

        ob_imb = imbalance(orderbook)
        spread = get_spread(orderbook)
        mid = get_mid_price(orderbook)

        features = {
            "return": float(ret),
            "volatility": float(volatility),
            "rsi": float(rsi),
            "ma25_dev": float(ma25_dev),
            "vwap_dev": float(vwap_dev),
            "vol_ratio": float(vol_ratio),
            "atr": float(atr),
            "imbalance": float(ob_imb),
            "spread": float(spread),
        }

        # Replace NaN with 0
        features = {k: 0.0 if (v != v) else v for k, v in features.items()}
        return features

    except Exception as exc:
        logger.warning(f"[features] build_features error: {exc}")
        return None


FEATURE_NAMES = [
    "return", "volatility", "rsi", "ma25_dev", "vwap_dev",
    "vol_ratio", "atr", "imbalance", "spread",
]
