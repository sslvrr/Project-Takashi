"""
Unit tests for the strategy and order flow modules.
"""

import pytest
import pandas as pd
import numpy as np

from strategy.indicators import compute_rsi, compute_ma, compute_vwap, enrich_dataframe
from strategy.orderflow import imbalance, sweep_detect, get_spread, get_mid_price, liquidity_zones
from strategy.core import generate_signal, session_filter
from strategy.filter import signal_filter
from strategy.features import build_features, FEATURE_NAMES


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _make_df(n: int = 100, trend: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    prices = 0.52 + np.cumsum(rng.normal(trend, 0.005, n))
    prices = np.clip(prices, 0.01, None)
    return pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=n, freq="5min"),
        "open": prices * 0.999,
        "high": prices * 1.003,
        "low": prices * 0.997,
        "close": prices,
        "volume": rng.uniform(100_000, 500_000, n),
    })


def _make_orderbook(bid_vol: float = 600_000, ask_vol: float = 400_000) -> dict:
    return {
        "bids": [[0.5195, bid_vol / 10]] * 10,
        "asks": [[0.5205, ask_vol / 10]] * 10,
    }


# ─── Indicator tests ─────────────────────────────────────────────────────────

def test_rsi_range():
    df = _make_df(100)
    rsi = compute_rsi(df["close"])
    assert rsi.dropna().between(0, 100).all()


def test_ma_length():
    df = _make_df(100)
    ma = compute_ma(df["close"], 25)
    assert len(ma) == 100


def test_vwap_positive():
    df = _make_df(100)
    vwap = compute_vwap(df)
    assert vwap.dropna().gt(0).all()


def test_enrich_dataframe_columns():
    df = _make_df(100)
    enriched = enrich_dataframe(df)
    for col in ["rsi", "ma25", "vwap", "atr", "vol_spike", "drop"]:
        assert col in enriched.columns, f"Missing column: {col}"


# ─── Order flow tests ─────────────────────────────────────────────────────────

def test_imbalance_buyer_dominated():
    ob = _make_orderbook(bid_vol=800_000, ask_vol=200_000)
    imb = imbalance(ob)
    assert imb > 0.7


def test_imbalance_seller_dominated():
    ob = _make_orderbook(bid_vol=200_000, ask_vol=800_000)
    imb = imbalance(ob)
    assert imb < 0.3


def test_sweep_detect_triggered():
    prev = _make_orderbook(bid_vol=600_000)
    curr = _make_orderbook(bid_vol=300_000)  # 50% drop → triggers
    assert sweep_detect(prev, curr, decay_threshold=0.70)


def test_sweep_detect_not_triggered():
    prev = _make_orderbook(bid_vol=600_000)
    curr = _make_orderbook(bid_vol=580_000)  # tiny drop
    assert not sweep_detect(prev, curr)


def test_get_spread():
    ob = _make_orderbook()
    spread = get_spread(ob)
    assert spread == pytest.approx(0.001, abs=1e-6)


def test_liquidity_zones():
    ob = _make_orderbook(bid_vol=500_000_000, ask_vol=500_000_000)
    zones = liquidity_zones(ob, min_size=1_000_000)
    assert isinstance(zones["support"], list)
    assert isinstance(zones["resistance"], list)


# ─── Signal tests ─────────────────────────────────────────────────────────────

def test_generate_signal_returns_signal_or_none():
    df = _make_df(100)
    ob = _make_orderbook()
    sig = generate_signal(df, ob, None, asset="XRP")
    assert sig is None or sig.direction in ("BUY", None)


def test_generate_signal_with_panic_conditions():
    """Force conditions that should produce a BUY signal."""
    df = _make_df(100)
    # Manufacture a large drop in the last bar
    df.loc[df.index[-1], "close"] = df["close"].iloc[-2] * 0.94  # -6% drop

    # High bid imbalance
    ob = _make_orderbook(bid_vol=1_000_000, ask_vol=200_000)
    sig = generate_signal(df, ob, None, asset="XRP")
    # score may not reach threshold without all conditions, but Signal should be returned
    assert sig is not None


def test_session_filter():
    assert session_filter(10)      # London
    assert session_filter(15)      # NY
    assert not session_filter(3)   # Asian
    assert not session_filter(22)  # Night


# ─── Filter tests ─────────────────────────────────────────────────────────────

def test_signal_filter_rejects_low_score():
    assert not signal_filter(score=3, volatility=0.005, spread=0.0001, asset="XRP")


def test_signal_filter_rejects_dead_market():
    assert not signal_filter(score=6, volatility=0.0001, spread=0.0001, asset="XRP")


def test_signal_filter_rejects_wide_spread():
    assert not signal_filter(score=6, volatility=0.005, spread=0.01, asset="XRP")


def test_signal_filter_passes():
    assert signal_filter(score=6, volatility=0.005, spread=0.0001, asset="XRP")


# ─── Feature tests ───────────────────────────────────────────────────────────

def test_build_features_returns_dict():
    df = _make_df(100)
    ob = _make_orderbook()
    features = build_features(df, ob)
    assert features is not None
    assert isinstance(features, dict)


def test_build_features_no_nan():
    df = _make_df(100)
    ob = _make_orderbook()
    features = build_features(df, ob)
    assert features is not None
    for k, v in features.items():
        assert v == v, f"NaN in feature: {k}"  # NaN != NaN


def test_feature_names_complete():
    df = _make_df(100)
    ob = _make_orderbook()
    features = build_features(df, ob)
    assert features is not None
    for name in FEATURE_NAMES:
        assert name in features, f"Missing feature: {name}"
