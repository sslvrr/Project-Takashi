"""
Deployment discipline — objective criteria before switching from paper to live.
"""


def can_go_live(performance: dict) -> tuple[bool, list[str]]:
    """
    Return (True, []) if performance metrics justify live deployment.
    Return (False, [reasons]) otherwise.
    """
    reasons = []

    if performance.get("trades", 0) < 50:
        reasons.append(f"Need ≥50 trades (have {performance.get('trades', 0)})")

    if performance.get("win_rate", 0) < 0.55:
        reasons.append(f"Win rate {performance.get('win_rate', 0):.1%} < 55%")

    if performance.get("pnl", 0) <= 0:
        reasons.append("Total PnL is not positive")

    if performance.get("max_drawdown", 1.0) > 0.15:
        reasons.append(f"Max drawdown {performance.get('max_drawdown', 0):.1%} > 15%")

    if performance.get("profit_factor", 0) < 1.2:
        reasons.append(f"Profit factor {performance.get('profit_factor', 0):.2f} < 1.2")

    return len(reasons) == 0, reasons
