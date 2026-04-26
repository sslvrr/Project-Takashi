"""
Multi-investor capital tracking and PnL allocation.
"""

from db.models import Investor
from db.session import get_session
from core.logger import logger


def get_all_investors() -> list[dict]:
    with get_session() as session:
        if session is None:
            return []
        rows = session.query(Investor).filter(Investor.active == True).all()
        return [{"name": r.name, "capital": r.capital} for r in rows]


def add_investor(name: str, capital: float) -> bool:
    with get_session() as session:
        if session is None:
            return False
        investor = Investor(name=name, capital=capital)
        session.add(investor)
    logger.info(f"[investors] Added {name} with ${capital:,.2f}")
    return True


def allocate_pnl(total_pnl: float) -> dict[str, float]:
    """
    Distribute total_pnl proportionally based on each investor's capital share.
    Returns {investor_name: allocated_pnl}
    """
    investors = get_all_investors()
    if not investors:
        return {}

    total_capital = sum(i["capital"] for i in investors)
    if total_capital <= 0:
        return {}

    distribution = {}
    for inv in investors:
        share = inv["capital"] / total_capital
        distribution[inv["name"]] = round(total_pnl * share, 4)

    return distribution
