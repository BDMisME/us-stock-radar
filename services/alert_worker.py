"""Alert Worker — drains the alerts queue to Telegram and/or Email.

A 'pending' alert is dispatched to its channel(s). If no channel is configured
the alert is marked 'skipped' (not 'failed') so an unconfigured install does
not accumulate failures. Partial success (one channel works, another not
configured) still counts as 'sent'.
"""
from __future__ import annotations

import time
from typing import Any

from alerts import email as email_channel
from alerts import telegram as telegram_channel
from config.settings import settings
from db import database as db
from services._logsetup import setup

logger = setup("alert_worker")


def _dispatch(alert: dict[str, Any]) -> str:
    """Return the resulting status for one alert: sent / skipped / failed."""
    channel = (alert.get("channel") or "all").lower()
    title = alert.get("title") or "us-stock-radar alert"
    message = alert.get("message") or ""
    text = f"<b>{title}</b>\n\n{message}"

    want_tg = channel in ("all", "telegram")
    want_email = channel in ("all", "email")

    any_configured = False
    any_sent = False

    if want_tg and telegram_channel.enabled():
        any_configured = True
        any_sent = telegram_channel.send_message(text) or any_sent
    if want_email and email_channel.enabled():
        any_configured = True
        any_sent = email_channel.send_email(title, message) or any_sent

    if not any_configured:
        return "skipped"
    return "sent" if any_sent else "failed"


def run_once() -> int:
    pending = db.pending_alerts(limit=50)
    for alert in pending:
        try:
            status = _dispatch(alert)
        except Exception as exc:
            logger.exception("dispatch failed for alert %s: %s", alert.get("id"), exc)
            status = "failed"
        db.mark_alert(alert["id"], status)
        logger.info("Alert %s -> %s", alert.get("id"), status)
    return len(pending)


def run_forever(interval_seconds: int = 15) -> None:
    if not (settings.telegram_enabled or settings.email_enabled):
        logger.warning("No notification channel configured; alerts will be marked 'skipped'.")
    logger.info("Alert worker starting (interval=%ss).", interval_seconds)
    while True:
        try:
            run_once()
        except Exception as exc:
            logger.exception("Alert worker loop error: %s", exc)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    db.init_db()
    run_forever(interval_seconds=settings.alert_worker_interval_seconds)
