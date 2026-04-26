"""
Order flow analysis — the closest approximation to Kotegawa's real edge.
All functions operate on raw order book dicts as returned by Binance WS.
"""

from collections import deque
from typing import Optional
from core.logger import logger


_ob_history: deque[dict] = deque(maxlen=20)


def record_orderbook(ob: dict) -> None:
    """Append snapshot to rolling history for temporal analysis."""
    if ob:
        _ob_history.append(ob)


# ─── Core imbalance ────────────────────────────────────────────────────────────

def imbalance(ob: dict, depth: int = 10) -> float:
    """
    Bid/ask volume imbalance over top-N levels.
    > 0.6 → strong buyers; < 0.4 → strong sellers; ~0.5 → neutral.
    Returns 0.5 on empty/invalid book.
    """
    try:
        bids = ob.get("bids", []) or ob.get("b", [])
        asks = ob.get("asks", []) or ob.get("a", [])
        bid_vol = sum(float(b[1]) for b in bids[:depth])
        ask_vol = sum(float(a[1]) for a in asks[:depth])
        total = bid_vol + ask_vol
        return bid_vol / total if total > 0 else 0.5
    except Exception as exc:
        logger.debug(f"[orderflow] imbalance error: {exc}")
        return 0.5


def weighted_imbalance(ob: dict, depth: int = 10) -> float:
    """
    Price-weighted imbalance — deeper levels near mid carry less weight.
    """
    try:
        bids = ob.get("bids", []) or ob.get("b", [])
        asks = ob.get("asks", []) or ob.get("a", [])
        best_bid = float(bids[0][0]) if bids else 0
        best_ask = float(asks[0][0]) if asks else 0
        mid = (best_bid + best_ask) / 2 if (best_bid and best_ask) else 0

        bid_w = sum(
            float(b[1]) * (1 - abs(float(b[0]) - mid) / mid)
            for b in bids[:depth] if mid > 0
        )
        ask_w = sum(
            float(a[1]) * (1 - abs(float(a[0]) - mid) / mid)
            for a in asks[:depth] if mid > 0
        )
        total = bid_w + ask_w
        return bid_w / total if total > 0 else 0.5
    except Exception as exc:
        logger.debug(f"[orderflow] weighted_imbalance error: {exc}")
        return 0.5


# ─── Sweep detection ───────────────────────────────────────────────────────────

def sweep_detect(prev_ob: dict, curr_ob: dict, decay_threshold: float = 0.70) -> bool:
    """
    Detect a bid-side liquidity sweep: top-5 bid volume dropped >30%.
    Signals: large buyer just got filled OR panic sellers swept through support.
    """
    try:
        prev_bids = prev_ob.get("bids", []) or prev_ob.get("b", [])
        curr_bids = curr_ob.get("bids", []) or curr_ob.get("b", [])
        prev_vol = sum(float(b[1]) for b in prev_bids[:5])
        curr_vol = sum(float(b[1]) for b in curr_bids[:5])
        if prev_vol <= 0:
            return False
        return curr_vol < prev_vol * decay_threshold
    except Exception as exc:
        logger.debug(f"[orderflow] sweep_detect error: {exc}")
        return False


def ask_sweep_detect(prev_ob: dict, curr_ob: dict, decay_threshold: float = 0.70) -> bool:
    """Detect an ask-side sweep (buying aggression wiping offers)."""
    try:
        prev_asks = prev_ob.get("asks", []) or prev_ob.get("a", [])
        curr_asks = curr_ob.get("asks", []) or curr_ob.get("a", [])
        prev_vol = sum(float(a[1]) for a in prev_asks[:5])
        curr_vol = sum(float(a[1]) for a in curr_asks[:5])
        if prev_vol <= 0:
            return False
        return curr_vol < prev_vol * decay_threshold
    except Exception as exc:
        logger.debug(f"[orderflow] ask_sweep error: {exc}")
        return False


# ─── Spoofing detection ────────────────────────────────────────────────────────

def spoofing_detected(threshold_multiplier: float = 5.0) -> bool:
    """
    Detect if any recent order book had an anomalously large bid order
    relative to history — a spoofing signal (ignore the trade).
    """
    if len(_ob_history) < 3:
        return False
    try:
        max_bids = []
        for ob in _ob_history:
            bids = ob.get("bids", []) or ob.get("b", [])
            if bids:
                max_bids.append(max(float(b[1]) for b in bids))
        if not max_bids:
            return False
        avg = sum(max_bids) / len(max_bids)
        return max_bids[-1] > threshold_multiplier * avg
    except Exception as exc:
        logger.debug(f"[orderflow] spoofing_detected error: {exc}")
        return False


# ─── Spread ────────────────────────────────────────────────────────────────────

def get_spread(ob: dict) -> float:
    """Return best ask − best bid."""
    try:
        bids = ob.get("bids", []) or ob.get("b", [])
        asks = ob.get("asks", []) or ob.get("a", [])
        if not bids or not asks:
            return 999.0
        return float(asks[0][0]) - float(bids[0][0])
    except Exception:
        return 999.0


def get_mid_price(ob: dict) -> float:
    try:
        bids = ob.get("bids", []) or ob.get("b", [])
        asks = ob.get("asks", []) or ob.get("a", [])
        if not bids or not asks:
            return 0.0
        return (float(bids[0][0]) + float(asks[0][0])) / 2
    except Exception:
        return 0.0


# ─── Liquidity heatmap ────────────────────────────────────────────────────────

def liquidity_zones(ob: dict, min_size: float = 10_000) -> dict:
    """
    Identify price levels with outsized resting liquidity.
    Returns support (large bids) and resistance (large asks).
    """
    try:
        bids = ob.get("bids", []) or ob.get("b", [])
        asks = ob.get("asks", []) or ob.get("a", [])
        large_bids = [
            {"price": float(b[0]), "volume": float(b[1])}
            for b in bids if float(b[1]) >= min_size
        ][:5]
        large_asks = [
            {"price": float(a[0]), "volume": float(a[1])}
            for a in asks if float(a[1]) >= min_size
        ][:5]
        return {"support": large_bids, "resistance": large_asks}
    except Exception as exc:
        logger.debug(f"[orderflow] liquidity_zones error: {exc}")
        return {"support": [], "resistance": []}


# ─── Composite score ──────────────────────────────────────────────────────────

def orderflow_score(ob: dict, prev_ob: Optional[dict] = None) -> dict:
    """
    Return a composite order flow dict with all signals for upstream use.
    """
    imb = imbalance(ob)
    sweep = sweep_detect(prev_ob, ob) if prev_ob else False
    spoof = spoofing_detected()
    spread = get_spread(ob)
    mid = get_mid_price(ob)
    zones = liquidity_zones(ob)

    return {
        "imbalance": imb,
        "sweep_detected": sweep,
        "spoofing": spoof,
        "spread": spread,
        "mid_price": mid,
        "liquidity_zones": zones,
        "buy_pressure": imb > 0.60 and not spoof,
    }
