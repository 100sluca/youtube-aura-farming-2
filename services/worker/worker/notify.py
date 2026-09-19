"""Alertes : ligne dans `alerts` + e-mail (Resend ou SMTP). Jamais bloquant pour le pipeline."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

import httpx
import structlog

from .config import Settings
from .db import Db

log = structlog.get_logger(__name__)


def send_email(settings: Settings, subject: str, body: str) -> bool:
    if settings.dry_run:
        log.info("dry_run.email", subject=subject)
        return True
    try:
        if settings.resend_api_key:
            r = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": "YouTube 2.0 <alerts@resend.dev>",
                    "to": [settings.alert_email_to],
                    "subject": subject,
                    "text": body,
                },
                timeout=15,
            )
            r.raise_for_status()
            return True
        if settings.smtp_host and settings.smtp_user and settings.smtp_pass:
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = settings.smtp_user, settings.alert_email_to, subject
            msg.set_content(body)
            with smtplib.SMTP_SSL(settings.smtp_host, 465, timeout=15) as s:
                s.login(settings.smtp_user, settings.smtp_pass)
                s.send_message(msg)
            return True
        log.warning("email.not_configured")
    except Exception as exc:  # noqa: BLE001
        log.error("email.failed", error=str(exc))
    return False


def flush_pending_alerts(db: Db, settings: Settings) -> int:
    """Envoie par mail les alertes `error`/`warning` pas encore envoyées (appelé par le planificateur)."""
    rows = db.fetch_all(
        "select id, severity, title, body from alerts where emailed_at is null "
        "and severity in ('error', 'warning') order by created_at limit 20"
    )
    sent = 0
    for a in rows:
        if send_email(settings, f"[YouTube 2.0] {a['severity'].upper()} · {a['title']}", a["body"] or ""):
            db.execute("update alerts set emailed_at = now() where id = %s", (a["id"],))
            sent += 1
    return sent
