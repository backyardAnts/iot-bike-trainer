"""SMTP email sender for workout summary reports."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any

from config_layer import settings  # noqa: F401  # Import loads .env when available.


def send_session_report_email(
    subject: str,
    body: str,
    html_body: str | None = None,
) -> dict[str, Any]:
    """Send a workout report email, or return a safe skipped/failed result."""
    if not _env_bool("EMAIL_ENABLED", False):
        print("EMAIL_ENABLED is false; generated workout report but skipped email send.")
        print(body)
        return {
            "status": "skipped_disabled",
            "sent": False,
            "email_to": os.getenv("EMAIL_TO", ""),
            "error": "",
        }

    smtp_host = os.getenv("EMAIL_SMTP_HOST", "").strip()
    smtp_port = _env_int("EMAIL_SMTP_PORT", 587)
    username = os.getenv("EMAIL_USERNAME", "").strip()
    password = os.getenv("EMAIL_PASSWORD", "")
    email_from = os.getenv("EMAIL_FROM", username).strip()
    email_to = os.getenv("EMAIL_TO", "").strip()

    missing = [
        name
        for name, value in (
            ("EMAIL_SMTP_HOST", smtp_host),
            ("EMAIL_FROM", email_from),
            ("EMAIL_TO", email_to),
        )
        if not value
    ]
    if missing:
        error = "Missing email configuration: {}".format(", ".join(missing))
        print(error)
        return {
            "status": "failed",
            "sent": False,
            "email_to": email_to,
            "error": error,
        }

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = email_from
    message["To"] = email_to
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
    except Exception as exc:
        error = "Failed to send workout summary email: {}".format(exc)
        print(error)
        return {
            "status": "failed",
            "sent": False,
            "email_to": email_to,
            "error": error,
        }

    print(f"Sent workout summary email to {email_to}.")
    return {
        "status": "sent",
        "sent": True,
        "email_to": email_to,
        "error": "",
    }


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default

    try:
        return int(value)
    except ValueError:
        return default
