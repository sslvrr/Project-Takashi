"""
MT5 live execution engine (EURUSD).
MetaTrader5 is Windows-only. On macOS/Linux the class loads but all
methods return empty dicts, allowing PAPER mode to function normally.
"""

import os
from core.logger import logger

try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore
    _MT5_AVAILABLE = False


MAGIC = 20240001   # Magic number identifying this bot's orders


class MT5Executor:
    def __init__(self):
        if not _MT5_AVAILABLE:
            logger.warning("[mt5_exec] MetaTrader5 not available. All operations are no-ops.")

    def _connected(self) -> bool:
        if not _MT5_AVAILABLE:
            return False
        return mt5.terminal_info() is not None

    def place_trade(
        self,
        symbol: str = "EURUSD",
        lot: float = 0.01,
        tp_pct: float = 0.02,
        sl_pct: float = 0.015,
        deviation: int = 20,
        comment: str = "TakashiV5",
    ) -> dict:
        if not self._connected():
            return {}

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"[mt5_exec] No tick data for {symbol}")
            return {}

        price = tick.ask
        sl = round(price * (1 - sl_pct), 5)
        tp = round(price * (1 + tp_pct), 5)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": mt5.ORDER_TYPE_BUY,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": deviation,
            "magic": MAGIC,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"[mt5_exec] Order send failed: retcode={result.retcode} {result.comment}")
            return {}

        logger.info(f"[mt5_exec] BUY {symbol} lot={lot} @ {price} TP={tp} SL={sl} | ticket={result.order}")
        return {
            "ticket": result.order,
            "symbol": symbol,
            "lot": lot,
            "price": price,
            "tp": tp,
            "sl": sl,
        }

    def close_position(self, ticket: int, symbol: str = "EURUSD", lot: float = 0.01) -> dict:
        if not self._connected():
            return {}

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {}

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": mt5.ORDER_TYPE_SELL,
            "position": ticket,
            "price": tick.bid,
            "deviation": 20,
            "magic": MAGIC,
            "comment": "TakashiV5-close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"[mt5_exec] Close failed: retcode={result.retcode} {result.comment}")
            return {}

        logger.info(f"[mt5_exec] CLOSE {symbol} ticket={ticket} @ {tick.bid}")
        return {"retcode": result.retcode, "ticket": result.order}

    def get_open_positions(self, symbol: str = "EURUSD") -> list[dict]:
        if not self._connected():
            return []
        positions = mt5.positions_get(symbol=symbol)
        if positions is None:
            return []
        return [p._asdict() for p in positions if p.magic == MAGIC]

    def get_account_equity(self) -> float:
        if not self._connected():
            return 0.0
        info = mt5.account_info()
        return float(info.equity) if info else 0.0
