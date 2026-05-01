"""
News blackout — blocks trading during high-impact economic events.
Fetches ForexFactory's public JSON calendar; caches for 1 hour.
Trading is blocked ±15 minutes around any High-impact event
for currencies that affect the traded asset.
"""

import time
import requests
from datetime import datetime, timedelta, timezone
from core.logger import logger

_URL           = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_BLACKOUT_MIN  = 15
_CACHE_TTL     = 3600   # seconds between calendar refreshes
_FAIL_TTL      = 300    # retry delay after a failed fetch

_cached_events: list[dict] = []
_cache_expires: float       = 0.0

# Map currency → assets affected by that currency's news
_CURRENCY_ASSETS: dict[str, set[str]] = {
    "USD": {"XAUUSD", "EURUSD", "XRP", "BTC", "ETH"},
    "EUR": {"EURUSD"},
    "XAU": {"XAUUSD"},
}


def _refresh() -> None:
    global _cached_events, _cache_expires
    try:
        resp = requests.get(
            _URL, timeout=8, headers={"User-Agent": "TakashiBot/1.0"}
        )
        resp.raise_for_status()
        _cached_events = [e for e in resp.json() if e.get("impact", "").lower() == "high"]
        _cache_expires = time.time() + _CACHE_TTL
        logger.debug(f"[news] ForexFactory: {len(_cached_events)} high-impact events this week")
    except Exception as exc:
        logger.debug(f"[news] Calendar fetch failed ({exc}) — blackout inactive")
        _cache_expires = time.time() + _FAIL_TTL


def is_blackout(asset: str) -> bool:
    """
    Return True if trading on `asset` should be blocked due to
    a high-impact news event within ±BLACKOUT_MIN minutes.
    Returns False on any fetch error (fail open, don't block).
    """
    if time.time() >= _cache_expires:
        _refresh()

    if not _cached_events:
        return False

    now    = datetime.now(timezone.utc)
    window = timedelta(minutes=_BLACKOUT_MIN)

    for event in _cached_events:
        currency = event.get("currency", "")
        if asset not in _CURRENCY_ASSETS.get(currency, set()):
            continue

        raw = event.get("date", "")
        if not raw:
            continue
        try:
            event_dt = datetime.fromisoformat(raw)
            if event_dt.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=timezone.utc)
            event_dt = event_dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue

        if abs(now - event_dt) <= window:
            logger.info(
                f"[news] Blackout active: {event.get('title','event')} "
                f"({currency}) at {event_dt.strftime('%H:%M')} UTC"
            )
            return True

    return False
