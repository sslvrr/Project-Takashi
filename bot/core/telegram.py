"""
Telegram alert integration.
Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in .env to activate.
"""

import requests
from config.settings import settings
from core.logger import logger


def send_telegram(message: str) -> bool:
    token = settings.TELEGRAM_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        logger.debug("[telegram] No credentials configured — skipping alert.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        response = requests.post(
            url,
            data={"chat_id": chat_id, "text": message},
            timeout=5,
        )
        if response.status_code != 200:
            logger.warning(f"[telegram] API error {response.status_code}: {response.text}")
            return False
        return True
    except requests.RequestException as exc:
        logger.warning(f"[telegram] Request failed: {exc}")
        return False
