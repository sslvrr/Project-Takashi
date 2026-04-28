"""
OANDA v20 REST feed — replaces MT5 for FX instruments on macOS/Linux.
Requires a free OANDA practice (or live) account.
Set OANDA_API_KEY and OANDA_ENVIRONMENT in .env.
"""

import requests
import pandas as pd
from datetime import timezone
from core.logger import logger
from config.settings import settings

# OANDA instrument name mapping (internal → OANDA format)
_INSTRUMENT_MAP = {
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "USDJPY": "USD_JPY",
    "AUDUSD": "AUD_USD",
    "USDCAD": "USD_CAD",
    "USDCHF": "USD_CHF",
    "XAUUSD": "XAU_USD",
}

_GRANULARITY_MAP = {
    "M1":  "M1",
    "M5":  "M5",
    "M15": "M15",
    "M30": "M30",
    "H1":  "H1",
    "H4":  "H4",
    "D1":  "D",
}

_BASE = {
    "practice": "https://api-fxpractice.oanda.com",
    "live":     "https://api-fxtrade.oanda.com",
}


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.OANDA_API_KEY}",
        "Content-Type":  "application/json",
    }


def _base_url() -> str:
    env = settings.OANDA_ENVIRONMENT.lower()
    return _BASE.get(env, _BASE["practice"])


def is_configured() -> bool:
    return bool(settings.OANDA_API_KEY)


def get_candles(
    symbol: str,
    granularity: str = "M5",
    count: int = 200,
) -> pd.DataFrame:
    """
    Fetch OHLCV candles from OANDA.
    symbol  : internal name e.g. 'EURUSD'
    Returns : DataFrame with columns [time, open, high, low, close, volume]
              or empty DataFrame on error.
    """
    if not is_configured():
        logger.warning("[oanda] OANDA_API_KEY not set — EURUSD feed disabled.")
        return pd.DataFrame()

    instrument = _INSTRUMENT_MAP.get(symbol.upper(), symbol.upper().replace("", "_", 3))
    gran = _GRANULARITY_MAP.get(granularity.upper(), "M5")

    url = f"{_base_url()}/v3/instruments/{instrument}/candles"
    params = {"count": count, "granularity": gran, "price": "M"}

    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=10)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logger.warning(f"[oanda] Candle fetch failed for {symbol}: {exc}")
        return pd.DataFrame()

    candles = resp.json().get("candles", [])
    if not candles:
        logger.warning(f"[oanda] No candles returned for {symbol}")
        return pd.DataFrame()

    rows = []
    for c in candles:
        if not c.get("complete", True):
            continue
        mid = c.get("mid", {})
        try:
            rows.append({
                "time":   pd.Timestamp(c["time"]).tz_convert(timezone.utc),
                "open":   float(mid["o"]),
                "high":   float(mid["h"]),
                "low":    float(mid["l"]),
                "close":  float(mid["c"]),
                "volume": int(c.get("volume", 0)),
            })
        except (KeyError, ValueError):
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    logger.debug(f"[oanda] {symbol} {gran} — {len(df)} bars fetched")
    return df


def get_latest_price(symbol: str) -> dict:
    """Return latest bid/ask/mid for a symbol."""
    if not is_configured():
        return {}

    instrument = _INSTRUMENT_MAP.get(symbol.upper(), symbol.upper())
    url = f"{_base_url()}/v3/instruments/{instrument}/candles"
    params = {"count": 1, "granularity": "S5", "price": "BA"}

    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=5)
        resp.raise_for_status()
        candles = resp.json().get("candles", [])
        if not candles:
            return {}
        c = candles[-1]
        bid = float(c.get("bid", {}).get("c", 0))
        ask = float(c.get("ask", {}).get("c", 0))
        return {
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "mid": round((bid + ask) / 2, 5),
            "spread": round(ask - bid, 5),
        }
    except Exception as exc:
        logger.debug(f"[oanda] Price fetch failed for {symbol}: {exc}")
        return {}
