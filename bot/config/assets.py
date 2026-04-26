"""
Asset registry — controls which markets are active.
Toggle at runtime by editing ASSETS or via the /assets API endpoint.
"""

ASSETS: dict[str, bool] = {
    "XRP": True,
    "EURUSD": True,
    "BTC": False,
    "ETH": False,
}

CRYPTO_SYMBOLS: dict[str, str] = {
    "XRP": "XRP/USD",
    "BTC": "BTC/USD",
    "ETH": "ETH/USD",
}

FX_SYMBOLS: dict[str, str] = {
    "EURUSD": "EURUSD",
}

CRYPTO_ASSETS = set(CRYPTO_SYMBOLS.keys())
FX_ASSETS = set(FX_SYMBOLS.keys())


def is_crypto(asset: str) -> bool:
    return asset in CRYPTO_ASSETS


def is_fx(asset: str) -> bool:
    return asset in FX_ASSETS


def get_exchange_symbol(asset: str) -> str:
    if is_crypto(asset):
        return CRYPTO_SYMBOLS[asset]
    return FX_SYMBOLS.get(asset, asset)


def enabled_assets() -> list[str]:
    from config.settings import settings
    active = {a.strip().upper() for a in settings.ACTIVE_ASSETS.split(",")}
    return [a for a, on in ASSETS.items() if on and a in active]
