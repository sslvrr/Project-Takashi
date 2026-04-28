"""
VENOM — ICT Multi-Timeframe Sweep + FVG Strategy (Python implementation).

Runs two independent 8-state machines per instance (bull + bear).
Call process(ltf_df, htf_df) on each new LTF bar.
Returns a Signal when entry conditions are met, None otherwise.

Timeframe pairs:
  Swing:    LTF=1H,  HTF=D   (poll interval ~3600s)
  Intraday: LTF=15M, HTF=4H  (poll interval ~900s)
  Scalp:    LTF=5M,  HTF=1H  (poll interval ~300s)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

import pandas as pd

from core.logger import logger


# ─── State containers ─────────────────────────────────────────────────────────

@dataclass
class _BullState:
    state: int = 0
    sl: Optional[float] = None      # sweep wick low (SL anchor)
    bft: Optional[float] = None     # bear FVG top
    bfb: Optional[float] = None     # bear FVG bottom
    gft: Optional[float] = None     # bull FVG top  (entry zone)
    gfb: Optional[float] = None     # bull FVG bottom
    choc: Optional[float] = None    # CHOC level (structural high at HTF sweep)


@dataclass
class _BearState:
    state: int = 0
    sh: Optional[float] = None      # sweep wick high (SL anchor)
    bft: Optional[float] = None     # bull FVG top
    bfb: Optional[float] = None     # bull FVG bottom
    gft: Optional[float] = None     # bear FVG top  (entry zone)
    gfb: Optional[float] = None     # bear FVG bottom
    choc: Optional[float] = None    # CHOC level (structural low at HTF sweep)


# ─── Main strategy class ──────────────────────────────────────────────────────

class VenomStrategy:
    """
    One instance per asset × timeframe combination.
    State persists across calls — do NOT reuse across assets/TFs.
    """

    def __init__(
        self,
        asset: str = "XAUUSD",
        ltf: str = "1H",
        htf: str = "D",
        ltf_sw: int = 10,
        htf_sw: int = 10,
        rr: float = 2.0,
        entry_type: str = "both",   # "aggressive" | "conservative" | "both"
    ):
        self.asset    = asset
        self.ltf      = ltf
        self.htf      = htf
        self.ltf_sw   = ltf_sw
        self.htf_sw   = htf_sw
        self.rr       = rr
        self.entry    = entry_type.lower()
        self.bull     = _BullState()
        self.bear     = _BearState()
        self._in_trade = False

    # ── Public API ────────────────────────────────────────────────────────────

    def process(
        self,
        ltf_df: pd.DataFrame,
        htf_df: pd.DataFrame,
    ):
        """
        Evaluate one LTF bar against HTF context.
        Returns a Signal (from strategy.core) or None.
        """
        if len(ltf_df) < max(self.ltf_sw + 3, 10):
            return None
        if len(htf_df) < self.htf_sw + 1:
            return None
        if self._in_trade:
            return None

        # ── HTF context ───────────────────────────────────────────────────
        # Exclude current (incomplete) HTF bar; use confirmed bars only
        htf_conf = htf_df.iloc[:-1]
        htf_ssl  = htf_conf["low"].rolling(self.htf_sw).min().iloc[-1]
        htf_bsl  = htf_conf["high"].rolling(self.htf_sw).max().iloc[-1]
        htf_lo   = htf_df["low"].iloc[-1]
        htf_hi   = htf_df["high"].iloc[-1]
        htf_bull = htf_lo < htf_ssl
        htf_bear = htf_hi > htf_bsl

        # ── LTF bars ──────────────────────────────────────────────────────
        cur  = ltf_df.iloc[-1]
        prev = ltf_df.iloc[-2]
        p2   = ltf_df.iloc[-3]

        o, h, l, c = cur["open"], cur["high"], cur["low"], cur["close"]
        ph, pl     = prev["high"], prev["low"]
        p2h, p2l   = p2["high"], p2["low"]

        # FVG detection (3-bar pattern)
        bear_fvg = h   < p2l   # current high < low[2] → imbalance gap below
        bull_fvg = l   > p2h   # current low  > high[2] → imbalance gap above

        # LTF swing high/low over `ltf_sw` bars (excluding current)
        sw_window = ltf_df["low"].iloc[-(self.ltf_sw + 1):-1]
        ltf_sl    = float(sw_window.min())
        sw_window_h = ltf_df["high"].iloc[-(self.ltf_sw + 1):-1]
        ltf_sh    = float(sw_window_h.max())

        # ── Run both state machines ────────────────────────────────────────
        sig = self._bull(h, l, c, ph, pl, p2h, p2l,
                         htf_bull, ltf_sl, bear_fvg, bull_fvg)
        if sig is None:
            sig = self._bear(h, l, c, ph, pl, p2h, p2l,
                             htf_bear, ltf_sh, bull_fvg, bear_fvg)
        if sig:
            sig.asset = self.asset
            self._in_trade = True

        return sig

    def on_trade_closed(self) -> None:
        """Call from the broker/engine when a VENOM trade settles."""
        self._in_trade = False
        self.bull = _BullState()
        self.bear = _BearState()

    # ── Bull state machine ────────────────────────────────────────────────────

    def _bull(self, h, l, c, ph, pl, p2h, p2l,
              htf_bull, ltf_sl, bear_fvg, bull_fvg):
        b = self.bull

        if b.state == 0:
            if htf_bull:
                b.state = 1
                b.choc  = h  # structural high at sweep time

        if b.state == 1:
            # Track bear FVG forming during the sell-off (non-exclusive check)
            if bear_fvg:
                b.bft, b.bfb = p2l, h
            # LTF secondary sweep
            if l < ltf_sl:
                b.sl    = l
                b.state = 2

        if b.state == 2:
            if b.bft is not None:
                b.state = 3
            elif bear_fvg:
                b.bft, b.bfb = p2l, h
                b.state = 3

        if b.state == 3:
            if b.bft and c > b.bft:
                b.state = 4  # close above bear FVG → reclaim

        if b.state == 4:
            if bull_fvg:
                b.gft, b.gfb = l, p2h
                b.state = 5
            elif b.bfb and c < b.bfb:
                b.state = 1

        if b.state == 5:
            if bull_fvg and l > (b.gft or 0):
                b.gft, b.gfb = l, p2h  # update to higher FVG
            if b.choc and c > b.choc:
                b.state = 7  # CHOC confirmed
            elif b.gfb and c < b.gfb:
                b.state = 1

        if b.state == 7:
            if bull_fvg and l > (b.gft or 0):
                b.gft, b.gfb = l, p2h  # follow price upward
            if b.gft and b.gfb and b.sl:
                in_fvg = (b.gfb <= c <= b.gft)
                if in_fvg and self._bull_entry_ok(b, c):
                    return self._bull_signal(b, c)
            if b.choc and c < b.choc:
                b.state = 0

        return None

    def _bull_entry_ok(self, b: _BullState, c: float) -> bool:
        if self.entry == "aggressive":
            return True
        # Conservative: FVG must be at or below 50% of (sl → choc) range
        if b.sl and b.choc and b.gft:
            mid = (b.sl + b.choc) * 0.5
            conservative_ok = b.gft <= mid
            if self.entry == "conservative":
                return conservative_ok
            return True   # "both" — accept either
        return True

    def _bull_signal(self, b: _BullState, c: float):
        from strategy.core import Signal
        sl  = b.sl - 0.0001
        rsk = max(c - sl, 1e-8)
        tp  = c + self.rr * rsk
        return Signal(
            asset="", direction="BUY", score=8, price=c,
            rsi=50.0, imbalance=0.0, vol_spike=False, drop=0.0,
            ma25_dev=0.0, vwap_dev=0.0, spread=0.0,
            sweep=True, spoofing=False,
            strategy="VENOM",
            sl_price=sl,
            tp_price=tp,
        )

    # ── Bear state machine ────────────────────────────────────────────────────

    def _bear(self, h, l, c, ph, pl, p2h, p2l,
              htf_bear, ltf_sh, bull_fvg, bear_fvg):
        s = self.bear

        if s.state == 0:
            if htf_bear:
                s.state = 1
                s.choc  = l  # structural low at sweep time

        if s.state == 1:
            if bull_fvg:
                s.bft, s.bfb = l, p2h
            if h > ltf_sh:
                s.sh    = h
                s.state = 2

        if s.state == 2:
            if s.bft is not None:
                s.state = 3
            elif bull_fvg:
                s.bft, s.bfb = l, p2h
                s.state = 3

        if s.state == 3:
            if s.bfb and c < s.bfb:
                s.state = 4

        if s.state == 4:
            if bear_fvg:
                s.gft, s.gfb = p2l, h
                s.state = 5
            elif s.bft and c > s.bft:
                s.state = 1

        if s.state == 5:
            if bear_fvg and p2l < (s.gft or float("inf")):
                s.gft, s.gfb = p2l, h
            if s.choc and c < s.choc:
                s.state = 7
            elif s.gft and c > s.gft:
                s.state = 1

        if s.state == 7:
            if bear_fvg and p2l < (s.gft or float("inf")):
                s.gft, s.gfb = p2l, h
            if s.gft and s.gfb and s.sh:
                in_fvg = (s.gfb <= c <= s.gft)
                if in_fvg and self._bear_entry_ok(s, c):
                    return self._bear_signal(s, c)
            if s.choc and c > s.choc:
                s.state = 0

        return None

    def _bear_entry_ok(self, s: _BearState, c: float) -> bool:
        if self.entry == "aggressive":
            return True
        if s.sh and s.choc and s.gfb:
            mid = (s.sh + s.choc) * 0.5
            conservative_ok = s.gfb >= mid
            if self.entry == "conservative":
                return conservative_ok
            return True
        return True

    def _bear_signal(self, s: _BearState, c: float):
        from strategy.core import Signal
        sl  = s.sh + 0.0001
        rsk = max(sl - c, 1e-8)
        tp  = c - self.rr * rsk
        return Signal(
            asset="", direction="SELL", score=8, price=c,
            rsi=50.0, imbalance=0.0, vol_spike=False, drop=0.0,
            ma25_dev=0.0, vwap_dev=0.0, spread=0.0,
            sweep=True, spoofing=False,
            strategy="VENOM",
            sl_price=sl,
            tp_price=tp,
        )
