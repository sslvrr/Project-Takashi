import sys
from pathlib import Path
from loguru import logger

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logger.remove()

logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>",
    level="INFO",
    colorize=True,
)

logger.add(
    LOG_DIR / "bot.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} — {message}",
    level="DEBUG",
    rotation="10 MB",
    retention="14 days",
    compression="zip",
    enqueue=True,
)

logger.add(
    LOG_DIR / "errors.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} — {message}",
    level="ERROR",
    rotation="5 MB",
    retention="30 days",
    compression="zip",
    enqueue=True,
)


def log(msg: str, level: str = "INFO") -> None:
    logger.log(level, msg)
