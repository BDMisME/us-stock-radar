"""Email notifications over SMTP (stdlib smtplib, STARTTLS)."""
from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from config.settings import settings

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return settings.email_enabled


def send_email(subject: str, body: str) -> bool:
    """Send a plain-text email. Returns True on success, False otherwise.

    Returns False when not configured so callers can mark alerts 'skipped'.
    """
    if not enabled():
        logger.info("Email not configured; skipping.")
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user or settings.email_to
    msg["To"] = settings.email_to

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.ehlo()
            try:
                server.starttls()
                server.ehlo()
            except smtplib.SMTPException:
                logger.debug("STARTTLS not available; continuing without it.")
            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(msg["From"], [settings.email_to], msg.as_string())
        return True
    except Exception as exc:
        logger.error("Email send failed: %s", exc)
        return False
