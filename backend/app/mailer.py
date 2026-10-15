"""Outgoing email (sign-up verification codes) over SMTP, with a log fallback."""

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


def send_verification_code(to: str, name: str, code: str, minutes: int) -> None:
    """Blocking; call from a worker thread."""
    if not smtp_configured():
        # Local demo mode: no mail server, so show the code to whoever runs the backend.
        log.warning("SMTP not configured. Verification code for %s: %s", to, code)
        return

    msg = EmailMessage()
    msg["Subject"] = f"{code} is your QueryECE verification code"
    msg["From"] = f"QueryECE <{SMTP_FROM}>"
    msg["To"] = to
    first = name.split()[0] if name.strip() else "there"
    msg.set_content(
        f"Hi {first},\n\nYour QueryECE verification code is {code}.\n"
        f"It expires in {minutes} minutes.\n\nIf you didn't sign up for QueryECE, ignore this email.\n"
    )
    msg.add_alternative(f"""\
<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:460px;margin:0 auto;padding:32px;color:#0f172a">
  <div style="font-size:20px;font-weight:700;color:#4338ca">QueryECE</div>
  <p style="margin-top:24px">Hi {first},</p>
  <p>Use this code to verify your email address:</p>
  <div style="font-size:34px;font-weight:700;letter-spacing:10px;background:#eef2ff;color:#312e81;
              border-radius:12px;padding:18px 0;text-align:center;margin:20px 0">{code}</div>
  <p style="color:#64748b;font-size:14px">It expires in {minutes} minutes. If you didn't sign up for QueryECE, you can ignore this email.</p>
</div>""", subtype="html")

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        log.exception("sending verification email to %s failed", to)
        raise MailError("Couldn't send the verification email. Please try again in a moment.") from exc
