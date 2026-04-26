"""
Risk reporting — structured summary of drawdown and exposure.
"""

from core.metrics import max_drawdown
from core.logger import logger


def risk_summary(equity: list[float], positions: list[dict]) -> str:
    dd = max_drawdown(equity)
    total_exposure = sum(p.get("size", 0) for p in positions)
    by_asset: dict[str, float] = {}
    for p in positions:
        sym = p.get("symbol", "?")
        by_asset[sym] = by_asset.get(sym, 0) + p.get("size", 0)

    lines = [
        f"⚠️ Risk Summary",
        f"Max Drawdown:    {dd:.2%}",
        f"Total Exposure:  {total_exposure:.4f}",
    ]
    for sym, sz in by_asset.items():
        lines.append(f"  {sym}: {sz:.4f}")

    return "\n".join(lines)
