"""Professor outreach: AI-drafted emails plus a per-professor status tracker.

Emails are never sent by the server; the student copies the draft or opens it
in their own mail client, then marks the card as sent.
"""

import logging
import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.llm import LLMUnavailable, complete
from app.auth import current_user
from app.config import GROQ_MODEL
from app.db.database import get_db
from app.db.models import Faculty, Outreach, Page, Project, User

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/outreach", tags=["outreach"])

STATUSES = ("drafted", "sent", "replied", "meeting", "accepted", "rejected")
CLOSED = ("accepted", "rejected")
FOLLOW_UP_AFTER_DAYS = 7
PURPOSES = (
    "Research internship / project",
    "B.Tech project (BTP)",
    "Summer internship",
    "M.Tech / PhD supervision",
    "Meeting to discuss their research",
    "Follow-up on my earlier email",
)
FOLLOW_UP = PURPOSES[-1]

DRAFT_PROMPT = """You write cold emails from an IIT Roorkee student to a professor in the ECE department.

Write one email for the purpose given. Rules:
- 140-210 words in the body. Formal but warm; plain sentences, no flattery, no buzzwords.
- Open with "Dear Prof. <surname>," and introduce the student in one line (name, programme, year, IIT Roorkee).
- Mention ONE or TWO specific things about the professor's work, taken ONLY from the professor material below (a research interest or a sponsored project title). Never invent papers, results, labs or details.
- Connect it to the student using ONLY the student profile below. Never invent skills, courses, grades or projects. If the profile is thin, keep that part short and honest.
- Make one clear request that matches the purpose, and say the CV is attached.
- Close with "Regards," then the student's name, programme and year, IIT Roorkee, and email, each on its own line.
- No bracketed placeholders.

Reply in exactly this format and nothing else:
SUBJECT: <subject line, under 12 words>
BODY:
<email body>"""


class DraftIn(BaseModel):
    faculty_id: int
    purpose: str = Field(default=PURPOSES[0], max_length=80)
    note: str = Field(default="", max_length=600)


class OutreachPatch(BaseModel):
    status: str | None = None
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=6000)
    notes: str | None = Field(default=None, max_length=2000)
    sent_on: date | None = None
    follow_up_on: date | None = None


def card_out(o: Outreach) -> dict:
    return {
        "id": o.id, "faculty_id": o.faculty_id, "professor_name": o.professor_name,
        "professor_email": o.professor_email, "purpose": o.purpose, "subject": o.subject,
        "body": o.body, "sent": o.sent or [], "status": o.status, "notes": o.notes,
        "sent_on": o.sent_on, "follow_up_on": o.follow_up_on, "updated_at": o.updated_at,
    }


def _own_card(card_id: int, user: User, db: Session) -> Outreach:
    card = db.get(Outreach, card_id)
    if not card or card.user_id != user.id:
        raise HTTPException(404, "Not found")
    return card


def _profile_excerpt(page_text: str | None, limit: int = 1500) -> str:
    """Research-relevant sections of the faculty profile page (skip contact/education boilerplate)."""
    if not page_text:
        return ""
    keep, out = False, []
    for line in page_text.splitlines():
        if line.startswith("## "):
            keep = any(k in line.lower() for k in ("research", "publication", "patent", "award", "background"))
        if keep:
            out.append(line)
    return "\n".join(out)[:limit]


def _professor_context(f: Faculty, db: Session) -> str:
    projects = (db.query(Project).filter_by(faculty_id=f.id)
                .order_by(Project.year.desc()).limit(6).all())
    page = db.query(Page).filter_by(url=f.profile_url).first() if f.profile_url else None
    lines = [f"Name: Prof. {f.name} ({f.designation or 'Faculty'}), ECE, IIT Roorkee",
             f"Research interests: {f.interests or 'not listed'}"]
    if projects:
        lines.append("Sponsored projects (as PI):")
        lines += [f"- {p.title} ({p.agency or 'agency n/a'}, {p.year or 'n.d.'})" for p in projects]
    excerpt = _profile_excerpt(page.text if page else None)
    if excerpt:
        lines.append("From the profile page:\n" + excerpt)
    return "\n".join(lines)


def _student_context(user: User) -> str:
    return "\n".join([
        f"Name: {user.name}",
        f"Programme and year: {user.program or 'not given'}, {user.year or 'not given'}",
        f"Email: {user.email}",
        f"Interests: {', '.join(user.interests or []) or 'not given'}",
        f"About: {user.bio or 'not given'}",
    ])


DRAFT_RE = re.compile(r"SUBJECT:\s*(?P<subject>.+?)\s*\n+\s*BODY:\s*\n?(?P<body>.+)", re.S | re.I)


def _parse_draft(text: str) -> tuple[str, str]:
    m = DRAFT_RE.search(text)
    if not m:
        raise LLMUnavailable("The draft came back in an unexpected format. Please try again.")
    subject = m.group("subject").strip().strip("*").strip()
    # Models often end lines with two spaces (markdown line breaks); drop them.
    body = "\n".join(line.rstrip() for line in m.group("body").strip().splitlines())
    return subject[:200], body


@router.get("")
def list_outreach(user: User = Depends(current_user), db: Session = Depends(get_db)):
    cards = db.query(Outreach).filter_by(user_id=user.id).order_by(Outreach.updated_at.desc()).all()
    return {"cards": [card_out(c) for c in cards], "statuses": STATUSES, "purposes": PURPOSES}


@router.post("/draft")
async def draft(body: DraftIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    prof = db.get(Faculty, body.faculty_id)
    if not prof:
        raise HTTPException(404, "Professor not found")
    card = db.query(Outreach).filter_by(user_id=user.id, faculty_id=prof.id).first()

    request = [f"Purpose: {body.purpose}"]
    if body.note.strip():
        request.append(f"Extra notes from the student (use them, don't invent beyond them): {body.note.strip()}")
    if body.purpose == FOLLOW_UP:
        if not card or not card.sent:
            raise HTTPException(400, "Mark your first email as sent before drafting a follow-up.")
        last = card.sent[-1]
        subject = last["subject"] if last["subject"].lower().startswith("re:") else f"Re: {last['subject']}"
        sent_on = date.fromisoformat(last["sent_on"]).strftime("%d %B %Y")
        request.append(
            f"This is a short polite follow-up (60-110 words) to the email sent on {sent_on}. "
            f"Don't repeat it; briefly restate the request. Use the subject '{subject}'. "
            f"Earlier email:\n{last['body']}")

    messages = [
        {"role": "system", "content": DRAFT_PROMPT},
        {"role": "user", "content": "\n\n".join([
            "PROFESSOR MATERIAL:\n" + _professor_context(prof, db),
            "STUDENT PROFILE:\n" + _student_context(user),
            "\n".join(request),
        ])},
    ]
    try:
        subject, text = _parse_draft(await complete(messages, model=GROQ_MODEL, max_tokens=1200, temperature=0.5))
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc))
    except Exception:
        log.exception("email draft failed")
        raise HTTPException(502, "Couldn't generate the draft. Please try again.")

    if card is None:
        card = Outreach(user_id=user.id, faculty_id=prof.id)
        db.add(card)
    card.professor_name, card.professor_email = prof.name, prof.email
    card.purpose, card.subject, card.body = body.purpose, subject, text
    db.commit()
    return card_out(card)


@router.patch("/{card_id}")
def update(card_id: int, patch: OutreachPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    card = _own_card(card_id, user, db)
    changes = patch.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] not in STATUSES:
        raise HTTPException(422, f"status must be one of: {', '.join(STATUSES)}")
    for field, value in changes.items():
        setattr(card, field, value)

    status = changes.get("status")
    if status == "sent":
        sent_on = changes.get("sent_on") or date.today()
        last = card.sent[-1] if card.sent else None
        if card.body and not (last and last["body"] == card.body):
            # Reassign rather than append so SQLAlchemy notices the JSON change.
            card.sent = [*(card.sent or []), {"subject": card.subject, "body": card.body,
                                              "sent_on": sent_on.isoformat()}]
        card.sent_on = sent_on
        if "follow_up_on" not in changes:
            card.follow_up_on = sent_on + timedelta(days=FOLLOW_UP_AFTER_DAYS)
    elif status in CLOSED or status == "replied":
        # The professor answered: no more nudging unless the student sets a date.
        if "follow_up_on" not in changes:
            card.follow_up_on = None
    db.commit()
    return card_out(card)


@router.delete("/{card_id}")
def delete(card_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own_card(card_id, user, db))
    db.commit()
    return {"ok": True}
