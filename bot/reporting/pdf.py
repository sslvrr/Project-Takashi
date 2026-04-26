"""
PDF report generator — uses reportlab to produce investor-grade reports.
"""

from pathlib import Path
from core.logger import logger

REPORT_DIR = Path(__file__).parent.parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)

try:
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    _REPORTLAB = True
except ImportError:
    _REPORTLAB = False
    logger.warning("[pdf] reportlab not installed. PDF export disabled.")


def generate_pdf(content: str, filename: str = "report.pdf") -> str:
    """
    Generate a simple PDF report from a text string.
    Returns the file path on success, empty string on failure.
    """
    if not _REPORTLAB:
        return ""

    path = REPORT_DIR / filename
    try:
        doc = SimpleDocTemplate(str(path), pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        for line in content.split("\n"):
            story.append(Paragraph(line, styles["Normal"]))
            story.append(Spacer(1, 6))
        doc.build(story)
        logger.info(f"[pdf] Report generated: {path}")
        return str(path)
    except Exception as exc:
        logger.error(f"[pdf] Generation error: {exc}")
        return ""


def generate_investor_pdf(report: dict) -> str:
    """Generate a structured investor report from a metrics dict."""
    lines = [
        "Project Takashi — Investor Report",
        "=" * 40,
        f"Total PnL:       ${report.get('total_pnl', 0):.4f}",
        f"Total Trades:    {report.get('trades', 0)}",
        f"Win Rate:        {report.get('win_rate', 0):.1%}",
        f"Sharpe Ratio:    {report.get('sharpe', 0):.3f}",
        f"Sortino Ratio:   {report.get('sortino', 0):.3f}",
        f"Max Drawdown:    {report.get('max_drawdown', 0):.2%}",
        f"Profit Factor:   {report.get('profit_factor', 0):.3f}",
        f"Expectancy/trade: ${report.get('expectancy', 0):.6f}",
    ]
    return generate_pdf("\n".join(lines), filename="investor_report.pdf")
