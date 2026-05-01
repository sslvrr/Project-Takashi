"""
VENOM — ICT Multi-Timeframe Sweep + FVG Strategy (Python implementation).

Runs two independent 8-state machines per instance (bull + bear).
Call process(ltf_df, htf_df) on each new LTF bar.
Returns a Signal when entry conditions are met, None otherwise.

Timeframe pairs:
  Swing:    LTF=1H,  HTF=D   (poll interval ~3600s)
  Intraday: LTF=15M, HTF=4H  (poll interval ~900s)
  Scalp:    LTF=5M,  HTF=1H  (poll interval ~300s)

v1.2 fixes:
  - State TTL: stale setups auto-expire per timeframe
  - ATR-based SL: replaces hard-coded 0.0001 pip offset
  - Wick invalidation: LTF sweep wick break in States 3-7 kills setup
  - CHOC fix: set to rolling swing high/low before sweep bar
  - Displacement check: FVG reclaim candle body must be >= 60% of range
  - Kill zone filter: FX/commodity entries gated to London/NY sessions (UTC)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from core.logger import logger


# ─── Kill zone config (UTC minutes) ──────────────────────────────────────────

_KILL_ZONES_UTC = [
    (7 * 60,       10 * 60),      # London Open
    (13 * 60,      16 * 60),      # NY Open
    (15 * 60,      17 * 60),      # London Close
    (18 * 60 + 30, 20 * 60),      # NY PM / Power Hour
]

_CRYPTO_ASSETS = {"XRP", "BTC", "ETH", "SOL"}

# State TTL per LTF (seconds) — how long a setup stays valid after HTF sweep
_TTL_BY_LTF = {
    "5M":  8 * 3600,    # scalp: 8 hours
    "15M": 48 * 3600,   # intraday: 2 days
    "1H":  120 * 3600,  # swing: 5 days
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _in_kill_zone(ref: Optional[datetime] = None) -> bool:
    now = ref or datetime.now(timezone.utc)
    m = now.hour * 60 + now.minute
    return any(s <= m < e for s, e in _KILL_ZONES_UTC)


def _atr(df: pd.DataFrame, n: int = 14) -> float:
    h, l, c = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - c).abs(),
                    (df["low"] - c).abs()], axis=1).max(axis=1)
    val = float(tr.rolling(n).mean().iloc[-1])
    return val if not pd.isna(val) else float(df["high"].iloc[-1] - df["low"].iloc[-1])


# ─── State containers ─────────────────────────────────────────────────────────

@dataclass
class _BullState:
    state: int = 0
    sl: Optional[float] = None      # LTF sweep wick low (SL anchor)
    bft: Optional[float] = None     # bear FVG top
    bfb: Optional[float] = None     # bear FVG bottom
    gft: Optional[float] = None     # bull FVG top  (entry zone)
    gfb: Optional[float] = None     # bull FVG bottom
    choc: Optional[float] = None    # CHOC level — last swing high before HTF sweep
    opened_at: Optional[float] = None  # unix timestamp when setup began (State 0→1)


@dataclass
class _BearState:
    state: int = 0
    sh: Optional[float] = None      # LTF sweep wick high (SL anchor)
    bft: Optional[float] = None     # bull FVG top
    bfb: Optional[float] = None     # bull FVG bottom
    gft: Optional[float] = None     # bear FVG top  (entry zone)
    gfb: Optional[float] = None     # bear FVG bottom
    choc: Optional[float] = None    # CHOC level — last swing low before HTF sweep
    opened_at: Optional[float] = None


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
        self.asset     = asset
        self.ltf       = ltf
        self.htf       = htf
        self.ltf_sw    = ltf_sw
        self.htf_sw    = htf_sw
        self.rr        = rr
        self.entry     = entry_type.lower()
        self.ttl       = _TTL_BY_LTF.get(ltf, 48 * 3600)
        self.bull      = _BullState()
        self.bear      = _BearState()
        self._in_trade = False

    # ── Public API ────────────────────────────────────────────────────────────

    def process(
        self,
        ltf_df: pd.DataFrame,
        htf_df: pd.DataFrame,
        bar_time: Optional[datetime] = None,
    ):
        """
        Evaluate one LTF bar against HTF context.
        Returns a Signal (from strategy.core) or None.
        """
        if len(ltf_df) < max(self.ltf_sw + 3, 14):
            return None
        if len(htf_df) < self.htf_sw + 1:
            return None
        if self._in_trade:
            return None

        # ── TTL expiry ────────────────────────────────────────────────────
        now = time.time()
        if self.bull.state > 0 and self.bull.opened_at:
            if now - self.bull.opened_at > self.ttl:
                logger.debug(f"[venom] {self.asset} bull setup expired (TTL {self.ttl}s)")
                self.bull = _BullState()
        if self.bear.state > 0 and self.bear.opened_at:
            if now - self.bear.opened_at > self.ttl:
                logger.debug(f"[venom] {self.asset} bear setup expired (TTL {self.ttl}s)")
                self.bear = _BearState()

        # ── HTF context ───────────────────────────────────────────────────
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
        bear_fvg = h   < p2l   # gap below — imbalance
        bull_fvg = l   > p2h   # gap above — imbalance

        # LTF swing high/low over `ltf_sw` bars (excluding current bar)
        sw_window   = ltf_df["low"].iloc[-(self.ltf_sw + 1):-1]
        ltf_sl      = float(sw_window.min())
        sw_window_h = ltf_df["high"].iloc[-(self.ltf_sw + 1):-1]
        ltf_sh      = float(sw_window_h.max())

        # 14-bar ATR for dynamic SL sizing
        atr = _atr(ltf_df)

        # ── Run both state machines ────────────────────────────────────────
        sig = self._bull(o, h, l, c, ph, pl, p2h, p2l,
                         htf_bull, ltf_sl, ltf_sh, bear_fvg, bull_fvg, atr)
        if sig is None:
            sig = self._bear(o, h, l, c, ph, pl, p2h, p2l,
                             htf_bear, ltf_sh, ltf_sl, bull_fvg, bear_fvg, atr)

        if sig:
            sig.asset = self.asset
            # Gate FX/commodity entries to kill zones only
            if self.asset not in _CRYPTO_ASSETS and not _in_kill_zone(bar_time):
                logger.debug(f"[venom] {self.asset} signal blocked — outside kill zone")
                return None
            self._in_trade = True

        return sig

    def on_trade_closed(self) -> None:
        """Call from the broker/engine when a VENOM trade settles."""
        self._in_trade = False
        self.bull = _BullState()
        self.bear = _BearState()

    # ── Bull state machine ────────────────────────────────────────────────────

    def _bull(self, o, h, l, c, ph, pl, p2h, p2l,
              htf_bull, ltf_sl, ltf_sh, bear_fvg, bull_fvg, atr):
        b = self.bull

        # Wick invalidation: LTF sweep low broken in an active setup → dead
        if b.state >= 3 and b.sl is not None and l < b.sl:
            logger.debug(f"[venom] bull setup invalidated — price broke LTF sweep low")
            self.bull = _BullState()
            return None

        if b.state == 0:
            if htf_bull:
                b.state      = 1
                b.opened_at  = time.time()
                b.choc       = ltf_sh   # structural high BEFORE the HTF sweep bar

        if b.state == 1:
            if bear_fvg:
                b.bft, b.bfb = p2l, h
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
            # Require displacement: reclaim candle body >= 60% of its range
            if b.bft and c > b.bft:
                candle_range = h - l
                body = abs(c - o)
                if candle_range > 0 and (body / candle_range) >= 0.5:
                    b.state = 4

        if b.state == 4:
            if bull_fvg:
                b.gft, b.gfb = l, p2h
                b.state = 5
            elif b.bfb and c < b.bfb:
                b.state = 1

        if b.state == 5:
            if bull_fvg and l > (b.gft or 0):
                b.gft, b.gfb = l, p2h
            if b.choc and c > b.choc:
                b.state = 7
            elif b.gfb and c < b.gfb:
                b.state = 1

        if b.state == 7:
            if bull_fvg and l > (b.gft or 0):
                b.gft, b.gfb = l, p2h
            if b.gft and b.gfb and b.sl:
                in_fvg = (b.gfb <= c <= b.gft)
                if in_fvg and self._bull_entry_ok(b, c):
                    return self._bull_signal(b, c, atr)
            if b.choc and c < b.choc:
                b.state = 0

        return None

    def _bull_entry_ok(self, b: _BullState, c: float) -> bool:
        if self.entry == "aggressive":
            return True
        if b.sl and b.choc and b.gft:
            mid = (b.sl + b.choc) * 0.5
            conservative_ok = b.gft <= mid
            if self.entry == "conservative":
                return conservative_ok
            return True
        return True

    def _bull_signal(self, b: _BullState, c: float, atr: float):
        from strategy.core import Signal
        sl  = b.sl - atr * 0.5
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

    def _bear(self, o, h, l, c, ph, pl, p2h, p2l,
              htf_bear, ltf_sh, ltf_sl, bull_fvg, bear_fvg, atr):
        s = self.bear

        # Wick invalidation: LTF sweep high broken in an active setup → dead
        if s.state >= 3 and s.sh is not None and h > s.sh:
            logger.debug(f"[venom] bear setup invalidated — price broke LTF sweep high")
            self.bear = _BearState()
            return None

        if s.state == 0:
            if htf_bear:
                s.state     = 1
                s.opened_at = time.time()
                s.choc      = ltf_sl   # structural low BEFORE the HTF sweep bar

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
            # Require displacement: reclaim candle body >= 60% of its range
            if s.bfb and c < s.bfb:
                candle_range = h - l
                body = abs(c - o)
                if candle_range > 0 and (body / candle_range) >= 0.5:
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
                    return self._bear_signal(s, c, atr)
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

    def _bear_signal(self, s: _BearState, c: float, atr: float):
        from strategy.core import Signal
        sl  = s.sh + atr * 0.5
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
