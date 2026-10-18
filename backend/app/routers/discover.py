"""Personalised views: faculty ranked for the student, faculty details, and the home dashboard."""

import asyncio
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db.database import get_db
from app.db.models import Faculty, Opportunity, Outreach, Project, Startup, User
from app.ingest.photos import local_photo_url, photo_path
from app.rag.personal import rank_faculty, top_matches
from app.routers.data import _rank_opportunities

router = APIRouter(prefix="/api", tags=["discover"])


def _faculty_card(row: dict, project_counts: dict[int, int]) -> dict:
    f = row["faculty"]
    return {
        "id": f.id, "name": f.name, "designation": f.designation, "email": f.email,
        "interests": f.interests, "image_url": local_photo_url(f.id), "profile_url": f.profile_url,
        "website": f.website, "projects": project_counts.get(f.id, 0),
        "match": row["match"], "matched": row["matched"], "reasons": row["reasons"],
    }


def _project_counts(db: Session) -> dict[int, int]:
    counts: dict[int, int] = {}
    for (fid,) in db.query(Project.faculty_id).filter(Project.faculty_id.isnot(None)):
        counts[fid] = counts.get(fid, 0) + 1
    return counts


@router.get("/me/faculty")
async def my_faculty(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """All faculty, best match for this student first."""
    faculty = db.query(Faculty).order_by(Faculty.name).all()
    ranked = await asyncio.to_thread(rank_faculty, faculty, user.interests or [])
    counts = _project_counts(db)
    return [_faculty_card(r, counts) for r in ranked]


@router.get("/faculty/{faculty_id}/photo")
def faculty_photo(faculty_id: int):
    """Saved copy of a faculty photo. Public, since <img> tags can't send the auth header."""
    path = photo_path(faculty_id)
    if not path:
        raise HTTPException(404, "No saved photo")
    # The URL carries ?v=<mtime>, so a changed photo gets a new URL and can be cached long.
    return FileResponse(path, headers={"Cache-Control": "public, max-age=604800, immutable"})


@router.get("/faculty/{faculty_id}")
def faculty_detail(faculty_id: int, _user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = db.get(Faculty, faculty_id)
    if not f:
        raise HTTPException(404, "Not found")
    projects = db.query(Project).filter_by(faculty_id=f.id).order_by(Project.year.desc()).all()
    startups = db.query(Startup).filter_by(faculty_id=f.id).all()
    return {
        "id": f.id, "name": f.name, "designation": f.designation, "email": f.email, "phone": f.phone,
        "website": f.website, "interests": f.interests, "image_url": local_photo_url(f.id), "profile_url": f.profile_url,
        "projects": [{"title": p.title, "agency": p.agency, "year": p.year, "co_pi": p.co_pi} for p in projects],
        "startups": [{"name": s.name, "website": s.website} for s in startups],
    }


def _starter_questions(user: User, top: list[dict]) -> list[str]:
    qs = []
    if top:
        f, r = top[0]["faculty"], top[0]
        topic = r["reasons"][0]["topic"] if r["reasons"] else (r["matched"][0] if r["matched"] else None)
        qs.append(f"What is Prof. {f.name} working on{f' in {topic}' if topic else ''}?")
    for interest in (user.interests or [])[:2]:
        qs.append(f"Which sponsored projects relate to {interest}?")
    if len(top) > 1:
        qs.append(f"Compare Prof. {top[0]['faculty'].name} and Prof. {top[1]['faculty'].name} for a research project")
    stage = (user.program or "").lower()
    if "b.tech" in stage or "btech" in stage:
        qs.append("How do I find a BTP supervisor in the ECE department?")
    qs.append("Are there any open RA / JRF positions right now?")
    return qs[:6]


@router.get("/home")
async def home(user: User = Depends(current_user), db: Session = Depends(get_db)):
    faculty = db.query(Faculty).all()
    interests = user.interests or []
    top = await asyncio.to_thread(top_matches, faculty, interests)
    counts = _project_counts(db)
    opps = db.query(Opportunity).filter(Opportunity.active.is_(True)).all()
    openings = await asyncio.to_thread(_rank_opportunities, opps, interests)
    cards = db.query(Outreach).filter_by(user_id=user.id).all()
    statuses = {}
    for c in cards:
        statuses[c.status] = statuses.get(c.status, 0) + 1
    due = [c.professor_name for c in cards if c.status == "sent" and c.follow_up_on and c.follow_up_on <= date.today()]
    return {
        "matches": [_faculty_card(r, counts) for r in top],
        "openings": openings[:4],
        "outreach": {"total": len(cards), "by_status": statuses, "follow_up_due": due},
        "questions": _starter_questions(user, top),
    }
