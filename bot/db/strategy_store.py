"""
Strategy configuration store — manages the strategy registry in DB.
Seeded automatically on startup; toggled via API or dashboard.
"""

from datetime import datetime, timezone
from db.models import StrategyConfig
from db.session import get_session
from core.logger import logger

_ALL_ASSETS = "XRP,EURUSD,XAUUSD,BTC,ETH"

_DEFAULTS = [
    {
        "name": "KOTEGAWA",
        "version": "v1.0",
        "timeframe": "5M",
        "assets": _ALL_ASSETS,
        "description": (
            "Kotegawa mean-reversion. Buys RSI oversold conditions with "
            "volume-spike and order-book imbalance confirmation. Named after "
            "Issei Kotegawa (CIS), the legendary Japanese intraday trader."
        ),
        "status": "PAPER",
        "pipeline": "ACTIVE",
        "enabled": True,
        "bt_win_rate": None,
        "bt_profit_factor": None,
        "bt_net_pnl": None,
        "bt_max_dd": None,
        "bt_trades": None,
    },
    {
        "name": "VENOM",
        "version": "v1.0",
        "timeframe": "5M/1H | 15M/4H | 1H/D",
        "assets": _ALL_ASSETS,
        "description": (
            "ICT Multi-Timeframe Sweep + FVG strategy. Detects HTF liquidity "
            "sweep → LTF secondary sweep → FVG reclaim → CHOC confirmation → "
            "retrace entry into bullish/bearish FVG. 8-state machine running "
            "simultaneous bull and bear setups."
        ),
        "status": "DEVELOPMENT",
        "pipeline": "BASELINE",
        "enabled": False,
        "bt_win_rate": 0.7143,
        "bt_profit_factor": 3.50,
        "bt_net_pnl": 137.72,
        "bt_max_dd": 61.19,
        "bt_trades": 7,
    },
]


def seed_default_strategies() -> None:
    with get_session() as session:
        if session is None:
            return
        for data in _DEFAULTS:
            existing = session.query(StrategyConfig).filter_by(name=data["name"]).first()
            if not existing:
                session.add(StrategyConfig(**data))
                logger.info(f"[strategy_store] Seeded: {data['name']}")


def get_all_strategies() -> list[dict]:
    with get_session() as session:
        if session is None:
            return _DEFAULTS
        rows = session.query(StrategyConfig).order_by(StrategyConfig.id).all()
        return [_row(r) for r in rows]


def toggle_strategy(name: str, enabled: bool) -> bool:
    with get_session() as session:
        if session is None:
            return False
        row = session.query(StrategyConfig).filter_by(name=name).first()
        if not row:
            return False
        row.enabled = enabled
        row.updated_at = datetime.now(timezone.utc)
        return True


def set_status(name: str, status: str) -> bool:
    with get_session() as session:
        if session is None:
            return False
        row = session.query(StrategyConfig).filter_by(name=name).first()
        if not row:
            return False
        row.status = status
        row.updated_at = datetime.now(timezone.utc)
        return True


def _row(r: StrategyConfig) -> dict:
    return {
        "name": r.name, "version": r.version,
        "timeframe": r.timeframe, "assets": r.assets,
        "description": r.description, "status": r.status,
        "pipeline": r.pipeline, "enabled": r.enabled,
        "bt_win_rate": r.bt_win_rate, "bt_profit_factor": r.bt_profit_factor,
        "bt_net_pnl": r.bt_net_pnl, "bt_max_dd": r.bt_max_dd,
        "bt_trades": r.bt_trades,
    }
