"""
MT5 data feed — polls EURUSD OHLCV and tick data.
MetaTrader5 package is Windows-only. On macOS/Linux the module
gracefully degrades and returns empty DataFrames so the rest of
the system can still run in PAPER mode.
"""

import pandas as pd
from datetime import datetime, timezone
from core.logger import logger

try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore
    _MT5_AVAILABLE = False
    logger.warning("[mt5_feed] MetaTrader5 package not available (macOS/Linux). MT5 feed disabled.")


def connect(login: int = 0, password: str = "", server: str = "") -> bool:
    if not _MT5_AVAILABLE:
        logger.warning("[mt5_feed] MT5 not available — skipping connect.")
        return False
    if not mt5.initialize():
        logger.error(f"[mt5_feed] mt5.initialize() failed: {mt5.last_error()}")
        return False
    if login:
        authorized = mt5.login(login, password=password, server=server)
        if not authorized:
            logger.error(f"[mt5_feed] mt5.login() failed: {mt5.last_error()}")
            return False
    logger.info("[mt5_feed] Connected to MT5.")
    return True


def disconnect() -> None:
    if _MT5_AVAILABLE and mt5:
        mt5.shutdown()
        logger.info("[mt5_feed] MT5 disconnected.")


def get_rates(symbol: str = "EURUSD", timeframe_str: str = "M5", n: int = 200) -> pd.DataFrame:
    """Return the last n closed bars as a DataFrame."""
    if not _MT5_AVAILABLE:
        return pd.DataFrame()

    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    tf = tf_map.get(timeframe_str.upper(), mt5.TIMEFRAME_M5)

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, n)
    if rates is None or len(rates) == 0:
        logger.warning(f"[mt5_feed] No rates returned for {symbol} {timeframe_str}")
        return pd.DataFrame()

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.rename(columns={"tick_volume": "volume"}, inplace=True)
    return df[["time", "open", "high", "low", "close", "volume"]]


def get_tick(symbol: str = "EURUSD") -> dict:
    """Return latest bid/ask tick."""
    if not _MT5_AVAILABLE:
        return {}
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {}
    return {
        "symbol": symbol,
        "bid": tick.bid,
        "ask": tick.ask,
        "last": tick.last,
        "time": datetime.fromtimestamp(tick.time, tz=timezone.utc),
        "spread": round(tick.ask - tick.bid, 5),
    }


def get_spread_pips(symbol: str = "EURUSD") -> float:
    """Return current spread in pips (EURUSD = 4 decimal precision)."""
    tick = get_tick(symbol)
    if not tick:
        return 999.0
    return round((tick["ask"] - tick["bid"]) * 10_000, 2)


def is_session_open(symbol: str = "EURUSD") -> bool:
    """Return True if the MT5 symbol is currently tradeable."""
    if not _MT5_AVAILABLE:
        return False
    info = mt5.symbol_info(symbol)
    if info is None:
        return False
    return info.trade_mode != mt5.SYMBOL_TRADE_MODE_DISABLED
