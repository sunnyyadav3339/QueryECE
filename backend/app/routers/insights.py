"""Seniors' insights: student-written tips that aren't on any website.

Lightly moderated: authors can delete their own, admins can hide any, and a
post hidden after REPORT_LIMIT distinct reports.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import current_user
from app.config import ADMIN_EMAILS
from app.db.database import get_db
from app.db.models import Faculty, Insight, InsightVote, User

router = APIRouter(prefix="/api/insights", tags=["insights"])

CATEGORIES = {
    "professor": "About a professor",
    "btp": "BTP / projects",
    "course": "Courses & electives",
    "interview": "Interviews & admissions",
    "internship": "Internships & placements",
    "general": "General",
}
REPORT_LIMIT = 3
DAILY_POST_LIMIT = 10


class InsightIn(BaseModel):
    category: str
    body: str = Field(min_length=20, max_length=800)
    faculty_id: int | None = None
    subject: str | None = Field(default=None, max_length=80)
    anonymous: bool = False


def _is_admin(user: User) -> bool:
    return user.email.lower() in ADMIN_EMAILS


def insight_out(i: Insight, me: User, counts: dict, mine: set, names: dict) -> dict:
    author = i.user
    return {
        "id": i.id, "category": i.category, "category_label": CATEGORIES.get(i.category, i.category),
        "faculty_id": i.faculty_id, "faculty_name": names.get(i.faculty_id), "subject": i.subject, "body": i.body,
        "author": "A senior" if i.anonymous or not author else author.name,
        "author_detail": None if i.anonymous or not author else " · ".join(x for x in (author.program, author.year) if x),
        "helpful": counts.get(i.id, 0), "voted": (i.id, "helpful") in mine, "reported": (i.id, "report") in mine,
        "mine": i.user_id == me.id, "can_delete": i.user_id == me.id or _is_admin(me),
        "created_at": i.created_at.replace(tzinfo=timezone.utc).isoformat() if i.created_at else None,
    }


def visible(db: Session):
    return db.query(Insight).filter(Insight.hidden.is_(False))


def _serialize(rows: list[Insight], me: User, db: Session) -> list[dict]:
    ids = [r.id for r in rows]
    counts = dict(db.query(InsightVote.insight_id, func.count()).filter(
        InsightVote.insight_id.in_(ids), InsightVote.kind == "helpful").group_by(InsightVote.insight_id)) if ids else {}
    mine = {(v.insight_id, v.kind) for v in db.query(InsightVote).filter(
        InsightVote.user_id == me.id, InsightVote.insight_id.in_(ids))} if ids else set()
    names = {f.id: f.name for f in db.query(Faculty.id, Faculty.name)}
    out = [insight_out(r, me, counts, mine, names) for r in rows]
    out.sort(key=lambda x: x["created_at"] or "", reverse=True)  # newest first...
    out.sort(key=lambda x: -x["helpful"])  # ...then most helpful first (stable sort)
    return out


@router.get("")
def list_insights(category: str | None = None, faculty_id: int | None = None,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = visible(db)
    if category:
        q = q.filter(Insight.category == category)
    if faculty_id:
        q = q.filter(Insight.faculty_id == faculty_id)
    rows = q.order_by(Insight.created_at.desc()).limit(200).all()
    return {"insights": _serialize(rows, user, db), "categories": CATEGORIES}


@router.post("")
def create(body: InsightIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.category not in CATEGORIES:
        raise HTTPException(422, "Unknown category")
    if body.faculty_id is not None and not db.get(Faculty, body.faculty_id):
        raise HTTPException(422, "Unknown professor")
    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    if db.query(Insight).filter(Insight.user_id == user.id, Insight.created_at >= day_ago).count() >= DAILY_POST_LIMIT:
        raise HTTPException(429, "You've shared a lot today. Try again tomorrow.")
    row = Insight(user_id=user.id, category=body.category, faculty_id=body.faculty_id,
                  subject=(body.subject or "").strip() or None, body=body.body.strip(), anonymous=body.anonymous)
    db.add(row)
    db.commit()
    return _serialize([row], user, db)[0]


def _get(insight_id: int, db: Session) -> Insight:
    row = db.get(Insight, insight_id)
    if not row or row.hidden:
        raise HTTPException(404, "Not found")
    return row


@router.post("/{insight_id}/helpful")
def toggle_helpful(insight_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = _get(insight_id, db)
    vote = db.get(InsightVote, (row.id, user.id, "helpful"))
    if vote:
        db.delete(vote)
    elif row.user_id != user.id:
        db.add(InsightVote(insight_id=row.id, user_id=user.id, kind="helpful"))
    db.commit()
    return _serialize([row], user, db)[0]


@router.post("/{insight_id}/report")
def report(insight_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = _get(insight_id, db)
    if not db.get(InsightVote, (row.id, user.id, "report")):
        db.add(InsightVote(insight_id=row.id, user_id=user.id, kind="report"))
        db.flush()
        reports = db.query(InsightVote).filter_by(insight_id=row.id, kind="report").count()
        if reports >= REPORT_LIMIT or _is_admin(user):
            row.hidden = True
    db.commit()
    return {"hidden": row.hidden}


@router.delete("/{insight_id}")
def delete(insight_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = _get(insight_id, db)
    if row.user_id != user.id and not _is_admin(user):
        raise HTTPException(403, "You can only delete your own posts")
    db.delete(row)
    db.commit()
    return {"ok": True}
