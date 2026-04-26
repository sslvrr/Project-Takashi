"""
Watchdog — auto-restarts the main bot process if it crashes.
Run as: python core/watchdog.py (separate process from main.py)
"""

import subprocess
import sys
import time
from pathlib import Path
from core.logger import logger

BOT_SCRIPT = Path(__file__).parent.parent / "main.py"
RESTART_DELAY = 5


def run_with_watchdog() -> None:
    logger.info("[watchdog] Starting bot with auto-restart enabled.")
    while True:
        logger.info(f"[watchdog] Launching: {BOT_SCRIPT}")
        try:
            proc = subprocess.run(
                [sys.executable, str(BOT_SCRIPT)],
                timeout=None,
            )
            exit_code = proc.returncode
            if exit_code == 0:
                logger.info("[watchdog] Bot exited cleanly. Not restarting.")
                break
            logger.warning(f"[watchdog] Bot exited with code {exit_code}. Restarting in {RESTART_DELAY}s…")
        except KeyboardInterrupt:
            logger.info("[watchdog] Interrupted. Stopping.")
            break
        except Exception as exc:
            logger.error(f"[watchdog] Unexpected error: {exc}. Restarting in {RESTART_DELAY}s…")

        time.sleep(RESTART_DELAY)


if __name__ == "__main__":
    run_with_watchdog()
