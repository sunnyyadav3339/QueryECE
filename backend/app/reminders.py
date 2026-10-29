"""Follow-up reminder emails for the outreach tracker.

Runs every few hours (so it catches up whenever the app is running); each due
date is emailed only once per card, tracked by Outreach.reminded_on.
"""

import html
import logging
from datetime import date, datetime, timedelta, timezone

from app.config import APP_URL
from app.db.database import SessionLocal
from app.db.models import Outreach, Update, User
from app.mailer import MailError, send_email

log = logging.getLogger(__name__)


def send_due_reminders() -> int:
    """Email each student about cards whose follow-up date has arrived. Returns emails sent."""
    today, sent = date.today(), 0
    with SessionLocal() as db:
        due = (db.query(Outreach).filter(Outreach.status == "sent", Outreach.follow_up_on <= today).all())
        by_user: dict[int, list[Outreach]] = {}
        for c in due:
            if c.reminded_on is None or c.reminded_on < c.follow_up_on:
                by_user.setdefault(c.user_id, []).append(c)
        for user_id, cards in by_user.items():
            user = db.get(User, user_id)
            if not user or not user.email_alerts:  # alerts switched off on the Profile page
                continue
            first = user.name.split()[0]
            lines = [f"- Prof. {c.professor_name}: \"{c.subject}\" (sent {c.sent_on:%d %b})" for c in cards]
            items = "".join(
                f"<li><b>Prof. {html.escape(c.professor_name)}</b>: {html.escape(c.subject)} "
                f'<span style="color:#64748b">(sent {c.sent_on:%d %b})</span></li>' for c in cards)
            n = len(cards)
            try:
                send_email(
                    user.email,
                    f"Follow-up due: {n} professor{'s haven' if n > 1 else ' hasn'}'t replied",
                    f"Hi {first},\n\nThese emails haven't had a reply yet:\n" + "\n".join(lines)
                    + f"\n\nA short, polite follow-up is fine. QueryECE can draft one: {APP_URL}/outreach\n",
                    f'<p style="margin-top:24px">Hi {html.escape(first)},</p>'
                    f"<p>These emails haven't had a reply yet:</p><ul>{items}</ul>"
                    "<p>A short, polite follow-up is fine, and QueryECE can draft it for you.</p>"
                    f'<p><a href="{APP_URL}/outreach" style="display:inline-block;background:#0071e3;color:#fff;'
                    'padding:10px 18px;border-radius:980px;text-decoration:none;font-weight:600">'
                    "Open outreach tracker</a></p>",
                )
            except MailError:
                continue  # try again next run
            for c in cards:
                c.reminded_on = today
            db.commit()
            sent += 1
    if sent:
        log.info("sent %s follow-up reminder email(s)", sent)
    return sent


DIGEST_EVERY = timedelta(hours=20)  # at most about once a day
DIGEST_LOOKBACK = timedelta(days=7)


def send_digests() -> int:
    """Daily "what's new for you" email: feed items since the last digest that match the student."""
    from app.routers.updates import personalise  # avoid a router import at module load

    now, sent = datetime.now(timezone.utc), 0
    with SessionLocal() as db:
        users = db.query(User).filter(User.email_alerts.is_(True), User.email_verified.is_(True)).all()
        for user in users:
            last = user.last_digest_at.replace(tzinfo=timezone.utc) if user.last_digest_at else None
            if last and now - last < DIGEST_EVERY:
                continue
            since = max(last or now - DIGEST_LOOKBACK, now - DIGEST_LOOKBACK)
            updates = db.query(Update).filter(Update.created_at >= since).order_by(Update.created_at.desc()).limit(100).all()
            matches = [u for u in personalise(updates, user.interests or []) if u["for_you"]][:8]
            user.last_digest_at = now
            db.commit()
            if not matches:
                continue
            first = user.name.split()[0]
            text_items = "\n".join(f"- {m['label']}: {m['title']} ({m['matched_interest']})" for m in matches)
            html_items = "".join(
                f'<li style="margin-bottom:10px"><span style="color:#6e6e73">{html.escape(m["label"])}</span><br>'
                f'<b>{html.escape(m["title"][:160])}</b> <span style="color:#0071e3">· {html.escape(m["matched_interest"])}</span></li>'
                for m in matches)
            try:
                send_email(
                    user.email, f"What's new for you on QueryECE ({len(matches)})",
                    f"Hi {first},\n\nNew on the ECE department website that matches your interests:\n{text_items}\n\n"
                    f"See everything: {APP_URL}/updates\nTurn these emails off on your Profile page.\n",
                    f'<p style="margin-top:24px">Hi {html.escape(first)},</p>'
                    f"<p>New on the ECE department website that matches your interests:</p><ul>{html_items}</ul>"
                    f'<p><a href="{APP_URL}/updates" style="display:inline-block;background:#0071e3;color:#fff;'
                    'padding:10px 18px;border-radius:980px;text-decoration:none">See what\'s new</a></p>'
                    '<p style="color:#86868b;font-size:13px">You can turn these emails off on your Profile page.</p>',
                )
                sent += 1
            except MailError:
                continue
    if sent:
        log.info("sent %s what's-new digest email(s)", sent)
    return sent
