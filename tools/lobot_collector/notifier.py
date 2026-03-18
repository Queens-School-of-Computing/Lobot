"""Email notifications for lobot-collector (startup / shutdown / errors)."""

import asyncio
import logging
import os
import smtplib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from .config import (
    EMAIL_ENABLED,
    SMTP_SERVER,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USERNAME,
    SMTP_PASSWORD,
    FROM_EMAIL,
    TO_EMAIL,
    OUTPUT_FILE,
    PODS_INTERVAL,
)

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="notifier")
_last_error_email_time: Optional[datetime] = None
EMAIL_COOLDOWN_MINUTES = 30


def _smtp_send(subject: str, body: str) -> None:
    """Blocking SMTP send — always called in the thread executor."""
    if not EMAIL_ENABLED:
        return
    try:
        msg = MIMEMultipart()
        msg["From"] = FROM_EMAIL
        msg["To"] = TO_EMAIL
        msg["Subject"] = f"Lobot Collector: {subject}"
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        if SMTP_USE_TLS:
            server.starttls()
        if SMTP_USERNAME and SMTP_PASSWORD:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        logger.info("Email sent to %s: %s", TO_EMAIL, subject)
    except Exception as exc:
        logger.error("Failed to send email (%s): %s", subject, exc)


async def send_startup_email() -> None:
    body = (
        f"Lobot Collector has started.\n\n"
        f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Host: {os.uname().nodename}\n"
        f"Interval: {PODS_INTERVAL}s\n"
        f"Output: {OUTPUT_FILE}\n"
    )
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_executor, _smtp_send, "Started", body)


async def send_shutdown_email(reason: str = "Normal shutdown") -> None:
    body = (
        f"Lobot Collector has stopped.\n\n"
        f"Stop Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Host: {os.uname().nodename}\n"
        f"Reason: {reason}\n"
    )
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_executor, _smtp_send, "Stopped", body)


async def send_error_email(
    error_type: str,
    error_message: str,
    error_count: int,
    traceback_info: str = "",
) -> None:
    """Send an error email, subject to a 30-minute per-process cooldown."""
    global _last_error_email_time
    now = datetime.now()
    if _last_error_email_time is not None:
        elapsed_minutes = (now - _last_error_email_time).total_seconds() / 60
        if elapsed_minutes < EMAIL_COOLDOWN_MINUTES:
            return
    _last_error_email_time = now

    body = (
        f"Lobot Collector encountered an error:\n\n"
        f"Time: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Error: {error_message}\n"
        f"Count: {error_count}\n"
    )
    if traceback_info:
        body += f"\nFull Traceback:\n{traceback_info}\n"
    body += "\nThe collector is still running and will retry.\n"

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_executor, _smtp_send, f"{error_type} (#{error_count})", body)
