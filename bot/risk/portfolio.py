"""
Portfolio engine — inverse-volatility capital allocation across assets.
Ensures higher-volatility assets receive smaller position sizes,
preserving consistent dollar-risk regardless of asset class.
"""

import numpy as np


def allocate_capital(
    signals: list[str],
    volatilities: dict[str, float],
) -> dict[str, float]:
    """
    Inverse-volatility weights.
    signals: list of asset names with active BUY signals
    volatilities: {asset: recent_vol} e.g. {"XRP": 0.05, "EURUSD": 0.008}
    Returns {asset: weight} where weights sum to 1.0
    """
    if not signals or not volatilities:
        return {}

    inv_vols = {}
    for asset in signals:
        vol = volatilities.get(asset, 1.0)
        inv_vols[asset] = 1.0 / max(vol, 1e-9)

    total = sum(inv_vols.values())
    return {asset: w / total for asset, w in inv_vols.items()}


def risk_parity(
    weights: dict[str, float],
    volatilities: dict[str, float],
) -> dict[str, float]:
    """
    Adjust weights by volatility to equalise dollar-risk per position.
    """
    if not weights or not volatilities:
        return weights

    adjusted = {}
    for asset, w in weights.items():
        vol = volatilities.get(asset, 1.0)
        adjusted[asset] = w / max(vol, 1e-9)

    total = sum(adjusted.values())
    if total <= 0:
        return weights

    return {k: v / total for k, v in adjusted.items()}


def exposure(positions: list[dict]) -> tuple[float, dict[str, float]]:
    """
    Compute total notional and per-asset breakdown.
    positions: list of dicts with 'symbol' and 'size' keys.
    """
    total = sum(p.get("size", 0) for p in positions)
    by_asset: dict[str, float] = {}
    for p in positions:
        sym = p.get("symbol", "UNKNOWN")
        by_asset[sym] = by_asset.get(sym, 0) + p.get("size", 0)
    return total, by_asset
