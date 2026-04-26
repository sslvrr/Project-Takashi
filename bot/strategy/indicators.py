"""
Technical indicator computation on OHLCV DataFrames.
All functions are pure — no side effects.
"""

import pandas as pd
import numpy as np
from typing import Optional


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_ma(close: pd.Series, period: int = 25) -> pd.Series:
    return close.rolling(window=period).mean()


def compute_ema(close: pd.Series, period: int = 25) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Intraday VWAP from OHLCV DataFrame."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    cumvol = df["volume"].cumsum()
    cumvtp = (typical * df["volume"]).cumsum()
    return cumvtp / cumvol.replace(0, np.nan)


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def compute_volume_spike(volume: pd.Series, period: int = 20, multiplier: float = 2.0) -> pd.Series:
    avg = volume.rolling(period).mean()
    return volume > (avg * multiplier)


def compute_intraday_drop(close: pd.Series) -> pd.Series:
    """Percentage change from previous bar."""
    return close.pct_change()


def compute_ma_deviation(close: pd.Series, ma: pd.Series) -> pd.Series:
    """How far price is from MA as a fraction: (close - MA) / MA."""
    return (close - ma) / ma.replace(0, np.nan)


def compute_vwap_deviation(close: pd.Series, vwap: pd.Series) -> pd.Series:
    return (close - vwap) / vwap.replace(0, np.nan)


def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add all required indicators to a raw OHLCV DataFrame.
    Modifies a copy and returns it.
    """
    df = df.copy()
    df["rsi"] = compute_rsi(df["close"])
    df["ma25"] = compute_ma(df["close"], 25)
    df["ema9"] = compute_ema(df["close"], 9)
    df["vwap"] = compute_vwap(df)
    df["atr"] = compute_atr(df)
    df["vol_spike"] = compute_volume_spike(df["volume"])
    df["drop"] = compute_intraday_drop(df["close"])
    df["ma25_dev"] = compute_ma_deviation(df["close"], df["ma25"])
    df["vwap_dev"] = compute_vwap_deviation(df["close"], df["vwap"])
    return df
