"""
Multi-account execution — fan out signals to multiple Coinbase subaccounts.
Accounts are loaded from environment (or overridden in tests).
"""

import os
from typing import Optional, Any
from core.logger import logger

try:
    import ccxt
    _CCXT_AVAILABLE = True
except ImportError:
    _CCXT_AVAILABLE = False


# Load multiple accounts from environment: ACCOUNT_1_KEY, ACCOUNT_1_SECRET, etc.
def _load_accounts() -> list[dict]:
    accounts = []
    i = 1
    while True:
        key = os.getenv(f"ACCOUNT_{i}_KEY")
        secret = os.getenv(f"ACCOUNT_{i}_SECRET")
        if not key or not secret:
            break
        accounts.append({"api_key": key, "secret": secret})
        i += 1
    return accounts


_ACCOUNTS = _load_accounts()


def execute_all(symbol: str, size: float, orderbook: Optional[dict] = None) -> list[dict]:
    """
    Place the same order across all configured sub-accounts.
    Returns list of order results.
    """
    if not _CCXT_AVAILABLE:
        logger.warning("[multi_account] ccxt not available.")
        return []

    results = []
    for acc in _ACCOUNTS:
        try:
            exchange = ccxt.coinbase({
                "apiKey": acc["api_key"],
                "secret": acc["secret"],
                "enableRateLimit": True,
            })
            order = exchange.create_market_buy_order(symbol, size)
            logger.info(f"[multi_account] Placed order on account …{acc['api_key'][-4:]}: {order.get('id')}")
            results.append(order)
        except Exception as exc:
            logger.error(f"[multi_account] Failed for account …{acc['api_key'][-4:]}: {exc}")
    return results
