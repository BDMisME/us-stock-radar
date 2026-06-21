"""Telegram Bot notifications via the HTTP Bot API (requests, no extra deps)."""
from __future__ import annotations

import logging

import requests

from config.settings import settings

logger = logging.getLogger(__name__)
_TIMEOUT = 10


def enabled() -> bool:
    return settings.telegram_enabled


def send_message(text: str) -> bool:
    """Send a Telegram message. Returns True on success, False otherwise.

    Returns False (not an exception) when not configured, so the alert worker
    can mark the alert 'skipped' rather than 'failed'.
    """
    if not enabled():
        logger.info("Telegram not configured; skipping.")
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("Telegram send failed: %s", exc)
        return False
