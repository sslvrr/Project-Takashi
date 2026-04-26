"""
FastAPI server — primary HTTP interface for Project Takashi.
Exposes health, system status, control endpoints, and investor metrics.
Run with: uvicorn api.server:app --host 0.0.0.0 --port 8000
"""

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

# ─── Shared system state (injected at startup from main.py) ──────────────────
_system_state: dict = {
    "mode": settings.MODE,
    "running": True,
    "kill_switch_triggered": False,
    "equity": 0.0,
    "trade_count": 0,
    "start_time": datetime.now(timezone.utc).isoformat(),
}


def update_state(**kwargs) -> None:
    _system_state.update(kwargs)


# ─── Endpoints ────────────────────────────────────────────────────────────────

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
    """Live performance metrics — wired to actual tracker in core/performance.py."""
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
                "entry": r.entry, "exit": r.exit, "pnl": r.pnl,
                "opened_at": str(r.opened_at), "reason": r.reason,
            }
            for r in rows
        ]}


@app.get("/latency")
def latency():
    from core.latency import get_latency_report
    return get_latency_report()
