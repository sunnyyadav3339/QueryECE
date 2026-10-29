"""Outgoing email over SMTP, with a log fallback for local demos."""

import html
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER

log = logging.getLogger(__name__)


class MailError(Exception):
    pass


def smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def _wrap(body_html: str) -> str:
    return (
        '<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:480px;margin:0 auto;'
        'padding:32px;color:#1d1d1f"><div style="font-size:20px;font-weight:700;color:#1d1d1f">QueryECE</div>'
        f"{body_html}</div>"
    )


def send_email(to: str, subject: str, text: str, body_html: str) -> None:
    """Blocking; call from a worker thread. Raises MailError on failure."""
    if not smtp_configured():
        log.warning("SMTP not configured. Email to %s: %s\n%s", to, subject, text)
        return
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, f"QueryECE <{SMTP_FROM}>", to
    msg.set_content(text)
    msg.add_alternative(_wrap(body_html), subtype="html")
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        log.exception("sending email to %s failed", to)
        raise MailError("Couldn't send the email. Please try again in a moment.") from exc


def send_code(to: str, name: str, code: str, minutes: int, purpose: str = "verify") -> None:
    first = html.escape(name.split()[0] if name.strip() else "there")
    action = "reset your password" if purpose == "reset" else "verify your email address"
    if not smtp_configured():
        log.warning("SMTP not configured. %s code for %s: %s", purpose, to, code)
        return
    send_email(
        to,
        f"{code} is your QueryECE {'password reset' if purpose == 'reset' else 'verification'} code",
        f"Hi {first},\n\nUse {code} to {action}. It expires in {minutes} minutes.\n\n"
        "If you didn't request this, ignore this email.\n",
        f'<p style="margin-top:24px">Hi {first},</p><p>Use this code to {action}:</p>'
        '<div style="font-size:34px;font-weight:700;letter-spacing:10px;background:#f5f5f7;color:#1d1d1f;'
        f'border-radius:12px;padding:18px 0;text-align:center;margin:20px 0">{code}</div>'
        f'<p style="color:#64748b;font-size:14px">It expires in {minutes} minutes. '
        "If you didn't request this, you can ignore this email.</p>",
    )
