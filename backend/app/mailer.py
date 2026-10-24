"""Sending email over SMTP (e.g. Gmail with an App Password).

Without SMTP_USERNAME (local development) messages are written to the server log instead, so a
reset link can still be clicked from there.
"""

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from app.config import settings

log = logging.getLogger(__name__)

SENDER_NAME = "Mindsketch.ai"


class MailError(RuntimeError):
    pass


def configured() -> bool:
    return bool(settings.smtp_username and settings.smtp_password)


def build_message(
    to: str, subject: str, text: str, html: str | None = None
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = formataddr(
        (SENDER_NAME, settings.mail_from or settings.smtp_username)
    )
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    return message


def _send_smtp(message: EmailMessage) -> None:
    context = ssl.create_default_context()
    timeout = settings.smtp_timeout_seconds
    if settings.smtp_port == 465:
        smtp = smtplib.SMTP_SSL(
            settings.smtp_host, 465, timeout=timeout, context=context
        )
    else:
        smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)
    with smtp:
        if settings.smtp_port != 465:
            smtp.starttls(context=context)
        # Google shows App Passwords in groups ("abcd efgh ..."); the spaces aren't part of it.
        smtp.login(settings.smtp_username, settings.smtp_password.replace(" ", ""))
        smtp.send_message(message)


async def send_email(to: str, subject: str, text: str, html: str | None = None) -> None:
    if not configured():
        log.warning(
            "SMTP is not configured; email to %s not sent:\n%s\n%s", to, subject, text
        )
        return
    message = build_message(to, subject, text, html)
    try:
        await asyncio.to_thread(_send_smtp, message)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"{exc.__class__.__name__}: {str(exc)[:200]}") from exc
    log.info("Sent %r to %s", subject, to)
