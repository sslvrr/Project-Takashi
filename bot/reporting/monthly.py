"""
Monthly report generator — produces a text summary and sends via Telegram.
"""

from core.metrics import win_rate, profit_factor, sharpe_ratio
from core.telegram import send_telegram
from core.logger import logger
from datetime import datetime, timezone


def monthly_report(trades: list[float]) -> str:
    if not trades:
        return "Monthly Report: No trades recorded."

    total_pnl = sum(trades)
    wr = win_rate(trades)
    pf = profit_factor(trades)
    sharpe = sharpe_ratio(trades)
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t < 0]
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0

    period = datetime.now(timezone.utc).strftime("%B %Y")

    report = (
        f"📈 Monthly Report — {period}\n"
        f"─────────────────────────\n"
        f"Total PnL:     ${total_pnl:.4f}\n"
        f"Total Trades:  {len(trades)}\n"
        f"Win Rate:      {wr:.1%}\n"
        f"Profit Factor: {pf:.2f}\n"
        f"Sharpe Ratio:  {sharpe:.2f}\n"
        f"Avg Win:       ${avg_win:.4f}\n"
        f"Avg Loss:      ${avg_loss:.4f}\n"
        f"─────────────────────────"
    )
    return report


def send_monthly_report(trades: list[float]) -> None:
    report = monthly_report(trades)
    logger.info(f"[reporting] Monthly report generated ({len(trades)} trades).")
    send_telegram(report)
