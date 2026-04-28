"""
FastAPI server — primary HTTP interface for Project Takashi.
Exposes health, system status, control endpoints, and investor metrics.
Run with: uvicorn api.server:app --host 0.0.0.0 --port 8000
"""

from collections import deque
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config.settings import settings
from config.assets import ASSETS, enabled_assets
from core.logger import logger

app = FastAPI(
    title="Project Takashi Trading System",
    description="Kotegawa mean-reversion bot — XRP + EURUSD",
    version="5.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Shared system state ──────────────────────────────────────────────────────
_system_state: dict = {
    "mode": settings.MODE,
    "running": True,
    "kill_switch_triggered": False,
    "equity": 0.0,
    "trade_count": 0,
    "start_time": datetime.now(timezone.utc).isoformat(),
}

_positions_state: list = []

_ml_state: dict = {
    "trained": False,
    "samples": 0,
    "top_features": {},
    "last_retrain": None,
}

_signal_feed: deque = deque(maxlen=100)
_close_requests: set = set()


# ─── State updaters (called from main.py / engine) ────────────────────────────

def update_state(**kwargs) -> None:
    _system_state.update(kwargs)


def update_positions(positions: list) -> None:
    global _positions_state
    _positions_state = positions


def update_ml_status(trained: bool, samples: int, top_features: dict) -> None:
    _ml_state.update({
        "trained": trained,
        "samples": samples,
        "top_features": top_features,
        "last_retrain": datetime.now(timezone.utc).isoformat() if trained else _ml_state.get("last_retrain"),
    })


def pop_close_requests() -> set:
    """Return and clear all pending manual close requests."""
    reqs = set(_close_requests)
    _close_requests.clear()
    return reqs


def push_signal(signal_info: dict) -> None:
    _signal_feed.appendleft({
        **signal_info,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ─── Core endpoints ───────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/status")
def status():
    return {
        **_system_state,
        "active_assets": enabled_assets(),
        "mode": settings.MODE,
    }


@app.get("/mode")
def get_mode():
    return {"mode": settings.MODE}


@app.post("/stop")
def stop():
    _system_state["running"] = False
    logger.warning("[api] Remote STOP issued via /stop endpoint.")
    return {"status": "stopped", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/start")
def start():
    if _system_state.get("kill_switch_triggered"):
        raise HTTPException(status_code=409, detail="Kill switch is triggered. Reset required.")
    _system_state["running"] = True
    logger.info("[api] Remote START issued via /start endpoint.")
    return {"status": "running"}


@app.get("/assets")
def get_assets():
    return ASSETS


class AssetToggle(BaseModel):
    asset: str
    enabled: bool


@app.post("/assets/toggle")
def toggle_asset(body: AssetToggle):
    if body.asset not in ASSETS:
        raise HTTPException(status_code=404, detail=f"Asset {body.asset} not found.")
    ASSETS[body.asset] = body.enabled
    logger.info(f"[api] Asset {body.asset} set to {'ON' if body.enabled else 'OFF'}")
    return {"asset": body.asset, "enabled": body.enabled}


@app.get("/metrics")
def metrics():
    from core.performance import get_metrics
    return get_metrics()


@app.get("/metrics/investor")
def investor_metrics():
    from core.investor_metrics import compute_investor_report
    return compute_investor_report()


@app.get("/trades/recent")
def recent_trades(limit: int = 20):
    from db.session import get_session
    from db.models import Trade
    with get_session() as session:
        if session is None:
            return {"trades": []}
        rows = session.query(Trade).order_by(Trade.id.desc()).limit(limit).all()
        return {"trades": [
            {
                "id": r.id, "symbol": r.symbol, "direction": r.direction,
                "entry": r.entry, "exit": r.exit, "size": r.size,
                "pnl": r.pnl, "tp": r.tp, "sl": r.sl,
                "score": r.score, "strategy": r.strategy,
                "r_multiple": r.r_multiple,
                "mode": r.mode, "reason": r.reason,
                "opened_at": str(r.opened_at), "closed_at": str(r.closed_at),
            }
            for r in rows
        ]}


@app.get("/latency")
def latency():
    from core.latency import get_latency_report
    return get_latency_report()


# ─── New endpoints ────────────────────────────────────────────────────────────

@app.get("/positions")
def get_positions():
    """Open paper positions from the live broker."""
    return {"positions": _positions_state}


@app.post("/positions/{position_id}/close")
def close_position(position_id: str):
    """Request a manual market close for a paper position."""
    _close_requests.add(position_id)
    logger.info(f"[api] Manual close requested for position {position_id}")
    return {"status": "close_requested", "id": position_id}


@app.get("/ml/status")
def ml_status():
    """ML model training status and feature importance."""
    return _ml_state


@app.get("/signals/recent")
def recent_signals(limit: int = 50):
    """Recent signal evaluations — both passed and vetoed."""
    return {"signals": list(_signal_feed)[:limit]}


@app.get("/go-live/status")
def go_live_status():
    """Check whether performance meets the live-trading deployment gates."""
    from core.performance import get_metrics, get_equity_curve
    from core.deployment import can_go_live
    from core.metrics import max_drawdown
    m = get_metrics()
    eq = get_equity_curve()
    dd = max_drawdown(eq) if eq else 0.0
    perf = {
        "trades":       m.get("trades", 0),
        "win_rate":     m.get("win_rate", 0.0),
        "pnl":          m.get("pnl", 0.0),
        "max_drawdown": dd,
        "profit_factor": m.get("profit_factor", 0.0),
    }
    ready, reasons = can_go_live(perf)
    return {"ready": ready, "reasons": reasons, "metrics": perf}


@app.get("/risk/summary")
def risk_summary_endpoint():
    """Live risk snapshot — drawdown, exposure, daily loss consumed."""
    from core.performance import get_equity_curve, get_pnl_series
    from core.metrics import max_drawdown
    from config.settings import settings
    eq = get_equity_curve()
    pnl = get_pnl_series()
    dd = max_drawdown(eq) if eq else 0.0
    total_exposure = sum(p.get("size", 0) for p in _positions_state)
    by_asset: dict = {}
    for p in _positions_state:
        sym = p.get("symbol", "?")
        by_asset[sym] = round(by_asset.get(sym, 0) + p.get("size", 0), 4)
    today_pnl = sum(pnl[-50:]) if pnl else 0.0
    return {
        "max_drawdown":       round(dd, 4),
        "total_exposure":     round(total_exposure, 4),
        "exposure_by_asset":  by_asset,
        "today_pnl":          round(today_pnl, 4),
        "daily_loss_limit":   settings.MAX_DAILY_LOSS,
        "daily_loss_used_pct": round(abs(min(today_pnl, 0)) / settings.MAX_DAILY_LOSS * 100, 1) if today_pnl < 0 else 0.0,
        "open_positions":     len(_positions_state),
        "max_positions":      settings.MAX_CONCURRENT_POSITIONS,
    }


@app.get("/health/detail")
def health_detail():
    """Detailed health — heartbeat age, alive status, uptime."""
    from core.health import check_health, seconds_since_heartbeat
    h = check_health(timeout_seconds=180)
    return {
        **h,
        "seconds_since_heartbeat": round(seconds_since_heartbeat(), 1),
        "start_time": _system_state.get("start_time"),
        "running": _system_state.get("running", False),
    }


@app.get("/arbitrage")
def arbitrage():
    """Cross-exchange price comparison (Coinbase vs Kraken)."""
    try:
        from data.multi_exchange import check_arbitrage
        return check_arbitrage("XRP/USD")
    except Exception as exc:
        return {"error": str(exc), "coinbase": 0, "kraken": 0, "spread_pct": 0, "opportunity": False}


@app.get("/monthly/report")
def get_monthly_report():
    """Generate monthly performance report."""
    from core.performance import get_pnl_series
    from reporting.monthly import monthly_report
    pnl = get_pnl_series()
    return {"report": monthly_report(pnl), "trades": len(pnl)}


@app.post("/monthly/send")
def send_monthly_report_endpoint():
    """Generate and send monthly report via Telegram."""
    from core.performance import get_pnl_series
    from reporting.monthly import send_monthly_report
    pnl = get_pnl_series()
    send_monthly_report(pnl)
    return {"status": "sent", "trades": len(pnl)}
