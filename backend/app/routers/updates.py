"""The "What's new" feed: changes the crawler noticed, flagged when they match the student."""

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db.database import get_db
from app.db.models import Faculty, Update, User
from app.rag.personal import TEXT_MATCH_THRESHOLD, match_texts

router = APIRouter(prefix="/api/updates", tags=["updates"])

KIND_LABEL = {
    "new_opening": "New opening",
    "new_project": "New sponsored project",
    "new_page": "New on the website",
    "updated_page": "Updated",
}


def update_text(u: Update) -> str:
    return f"{u.title}\n{u.detail or ''}"


def personalise(updates: list[Update], interests: list[str]) -> list[dict]:
    scores = match_texts([(str(u.id), update_text(u)) for u in updates], interests)
    out = []
    for u in updates:
        sim, interest = scores.get(str(u.id), (0.0, None))
        for_you = sim >= TEXT_MATCH_THRESHOLD
        out.append({
            "id": u.id, "kind": u.kind, "label": KIND_LABEL.get(u.kind, u.kind), "title": u.title, "url": u.url,
            "detail": u.detail, "faculty_id": u.faculty_id,
            "created_at": u.created_at.replace(tzinfo=timezone.utc).isoformat() if u.created_at else None,
            "for_you": for_you, "matched_interest": interest if for_you else None,
        })
    return out


@router.get("")
async def list_updates(days: int = 60, user: User = Depends(current_user), db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=min(max(days, 1), 365))
    updates = (db.query(Update).filter(Update.created_at >= since).order_by(Update.created_at.desc())
               .limit(200).all())
    names = {f.id: f.name for f in db.query(Faculty.id, Faculty.name)}
    items = await asyncio.to_thread(personalise, updates, user.interests or [])
    for it in items:
        it["faculty_name"] = names.get(it["faculty_id"])
    return items
