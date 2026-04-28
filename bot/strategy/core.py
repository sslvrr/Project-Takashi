"""
Kotegawa V5 signal engine.
Combines price action, order flow, and optional ML prediction into one
composite score. Returns a typed Signal object.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

import pandas as pd

from strategy.indicators import enrich_dataframe
from strategy.orderflow import (
    imbalance,
    sweep_detect,
    spoofing_detected,
    get_spread,
    get_mid_price,
)
from config.settings import settings
from core.logger import logger


@dataclass
class Signal:
    asset: str
    direction: str              # "BUY" | None
    score: int
    price: float
    rsi: float
    imbalance: float
    vol_spike: bool
    drop: float
    ma25_dev: float
    vwap_dev: float
    spread: float
    sweep: bool
    spoofing: bool
    ml_prediction: Optional[int] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    # Extended fields for non-Kotegawa strategies
    strategy: Optional[str] = None
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None

    @property
    def is_valid(self) -> bool:
        if self.strategy and self.strategy != "KOTEGAWA":
            # VENOM and other strategies gate on direction + no spoofing
            return self.direction in ("BUY", "SELL") and not self.spoofing
        return self.direction == "BUY" and not self.spoofing

    def to_dict(self) -> dict:
        return {
            "asset": self.asset,
            "direction": self.direction,
            "score": self.score,
            "price": self.price,
            "rsi": self.rsi,
            "imbalance": self.imbalance,
            "vol_spike": self.vol_spike,
            "drop": self.drop,
            "ma25_dev": self.ma25_dev,
            "vwap_dev": self.vwap_dev,
            "spread": self.spread,
            "sweep": self.sweep,
            "spoofing": self.spoofing,
            "ml_prediction": self.ml_prediction,
            "timestamp": self.timestamp.isoformat(),
        }


def generate_signal(
    df: pd.DataFrame,
    orderbook: dict,
    prev_ob: Optional[dict],
    asset: str = "XRP",
    ml_prediction: Optional[int] = None,
) -> Optional[Signal]:
    """
    Core Kotegawa signal generator.

    Score accumulation:
      RSI < oversold          +1
      Volume spike            +1
      Panic drop              +2
      MA25 deviation >20%     +2
      OB imbalance > thresh   +2
      Liquidity sweep         +2
      ML confirms (if avail)  +1
    Threshold: 5 pts minimum.
    """
    if df is None or len(df) < 26:
        return None

    enriched = enrich_dataframe(df)
    row = enriched.iloc[-1]

    rsi = float(row.get("rsi", 50))
    vol_spike = bool(row.get("vol_spike", False))
    drop = float(row.get("drop", 0))
    ma25_dev = float(row.get("ma25_dev", 0))
    vwap_dev = float(row.get("vwap_dev", 0))
    price = float(row.get("close", 0))

    ob_imb = imbalance(orderbook)
    sweep = sweep_detect(prev_ob, orderbook) if prev_ob else False
    spoof = spoofing_detected()
    spread = get_spread(orderbook)

    score = 0

    # RSI oversold
    if rsi < settings.RSI_OVERSOLD:
        score += 1

    # Volume spike
    if vol_spike:
        score += 1

    # Panic drop (intraday)
    if drop <= settings.PANIC_DROP_THRESHOLD:
        score += 2

    # MA25 deep deviation (>20% below)
    if ma25_dev <= -0.20:
        score += 2

    # Order book imbalance
    if ob_imb >= settings.OB_IMBALANCE_THRESHOLD:
        score += 2

    # Liquidity sweep
    if sweep:
        score += 2

    # ML layer confirmation
    if ml_prediction == 1:
        score += 1

    direction = "BUY" if score >= settings.MIN_SIGNAL_SCORE else None

    # Spoofing veto — abort regardless of score
    if spoof:
        direction = None
        logger.debug(f"[strategy] Spoofing detected for {asset}, signal vetoed.")

    sig = Signal(
        asset=asset,
        direction=direction,
        score=score,
        price=price,
        rsi=rsi,
        imbalance=ob_imb,
        vol_spike=vol_spike,
        drop=drop,
        ma25_dev=ma25_dev,
        vwap_dev=vwap_dev,
        spread=spread,
        sweep=sweep,
        spoofing=spoof,
        ml_prediction=ml_prediction,
    )

    if direction:
        logger.info(
            f"[strategy] SIGNAL {asset} {direction} | score={score} | "
            f"rsi={rsi:.1f} | imb={ob_imb:.2f} | drop={drop*100:.2f}% | "
            f"price={price}"
        )

    return sig


def session_filter(hour_utc: int) -> bool:
    """
    Return True during London (08–12 UTC) and New York (13–17 UTC) sessions.
    Avoids low-liquidity Asian session for EURUSD.
    """
    return 8 <= hour_utc < 18
