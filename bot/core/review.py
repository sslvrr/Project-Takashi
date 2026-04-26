"""
Periodic review engine — generates weekly performance summaries
and sends them via Telegram.
"""

from core.metrics import win_rate, profit_factor, max_drawdown
from core.telegram import send_telegram
from core.logger import logger


def weekly_review(trades: list[float], equity: list[float]) -> dict:
    """Compute and return weekly stats dict."""
    wr = win_rate(trades)
    pf = profit_factor(trades)
    dd = max_drawdown(equity)
    total_pnl = sum(trades)

    report = {
        "trades": len(trades),
        "pnl": round(total_pnl, 4),
        "win_rate": round(wr, 4),
        "profit_factor": round(pf, 3),
        "max_drawdown": round(dd, 4),
    }
    return report


def send_weekly_summary(trades: list[float], equity: list[float]) -> None:
    report = weekly_review(trades, equity)
    msg = (
        f"📊 Weekly Report\n"
        f"Trades: {report['trades']}\n"
        f"PnL: ${report['pnl']:.4f}\n"
        f"Win Rate: {report['win_rate']:.1%}\n"
        f"Profit Factor: {report['profit_factor']:.2f}\n"
        f"Max Drawdown: {report['max_drawdown']:.2%}"
    )
    logger.info(f"[review] {msg.replace(chr(10), ' | ')}")
    send_telegram(msg)
