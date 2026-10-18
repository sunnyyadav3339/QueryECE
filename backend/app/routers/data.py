"""Read-only department data for the UI, plus crawl status/trigger."""

import asyncio
import re
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.auth import admin_user, current_user
from app.db.database import get_db
from app.db.models import CrawlRun, Faculty, Opportunity, Page, Project, User
from app.ingest import pipeline
from app.ingest.photos import local_photo_url
from app.rag import index
from app.rag.embeddings import cosine, embed_passages, embed_query

router = APIRouter(prefix="/api", tags=["data"])


@router.get("/faculty")
def faculty(db: Session = Depends(get_db)):
    rows = db.query(Faculty).order_by(Faculty.name).all()
    return [{"id": f.id, "name": f.name, "designation": f.designation, "email": f.email, "phone": f.phone,
             "website": f.website, "interests": f.interests, "profile_url": f.profile_url,
             "image_url": local_photo_url(f.id)} for f in rows]


# Measured with bge-small: interest vs. a clearly relevant advert ~0.72-0.76,
# vs. an unrelated advert ~0.45-0.60. Map 0.55 -> 0% and 0.80 -> 100%.
MATCH_FLOOR, MATCH_CEIL = 0.55, 0.80
MIN_DISPLAY_MATCH = 30
BOILERPLATE_RE = re.compile(r"^.*?(?:position\(s\) of|Position in)\s*", re.I)


def _match_percent(score: float) -> int:
    return max(0, min(99, round((score - MATCH_FLOOR) / (MATCH_CEIL - MATCH_FLOOR) * 100)))


def _role_text(title: str) -> str:
    """Drop the 'Advertisement dated ...: Advertisement for the position(s) of' prefix
    every advert shares; it drowns out the actual role in the embedding."""
    return BOILERPLATE_RE.sub("", title, count=1) or title


def _rank_opportunities(opps: list[Opportunity], interests: list[str]) -> list[dict]:
    """Score each advert by its best match against any of the student's interests."""
    scores = [(0.0, None)] * len(opps)
    if interests and opps:
        interest_vecs = [embed_query(i) for i in interests]
        opp_vecs = embed_passages([f"{_role_text(o.title)}\n{(o.details or '')[:600]}" for o in opps])
        scores = []
        for vec in opp_vecs:
            sims = [cosine(vec, iv) for iv in interest_vecs]
            best = max(range(len(sims)), key=sims.__getitem__)
            scores.append((sims[best], interests[best]))
    out = []
    for opp, (score, interest) in zip(opps, scores):
        match = _match_percent(score)
        shown = interest is not None and match >= MIN_DISPLAY_MATCH
        out.append({
            "id": opp.id, "kind": opp.kind, "title": opp.title, "department": opp.department,
            "is_ece": opp.is_ece, "posted_on": opp.posted_on, "deadline": opp.deadline, "url": opp.url,
            "match": match if shown else None,
            "matched_interest": interest if shown else None,
        })
    out.sort(key=lambda o: (not o["is_ece"], -(o["match"] or 0)))
    return out


@router.get("/opportunities")
async def opportunities(user: User = Depends(current_user), db: Session = Depends(get_db)):
    opps = db.query(Opportunity).filter(Opportunity.active.is_(True)).all()
    return await asyncio.to_thread(_rank_opportunities, opps, user.interests or [])


def _utc(dt: datetime | None) -> str | None:
    """SQLite drops tzinfo; values are stored in UTC, so re-attach it for the client."""
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


@router.get("/status")
def status(db: Session = Depends(get_db)):
    last = db.query(CrawlRun).order_by(CrawlRun.id.desc()).first()
    last_ok = db.query(CrawlRun).filter_by(status="ok").order_by(CrawlRun.id.desc()).first()
    return {
        "crawl_running": pipeline.is_running(),
        "last_run": {"status": last.status, "started_at": _utc(last.started_at), "finished_at": _utc(last.finished_at),
                     "pages_fetched": last.pages_fetched, "pages_changed": last.pages_changed,
                     "error": last.error} if last else None,
        "last_success_at": _utc(last_ok.finished_at) if last_ok else None,
        "pages": db.query(Page).filter(Page.active.is_(True)).count(),
        "chunks": index.count(),
        "faculty": db.query(Faculty).count(),
        "projects": db.query(Project).count(),
        "opportunities": db.query(Opportunity).filter(Opportunity.active.is_(True)).count(),
    }


@router.post("/admin/crawl")
def trigger_crawl(background: BackgroundTasks, _admin: User = Depends(admin_user)):
    if pipeline.is_running():
        return {"status": "already_running"}
    background.add_task(pipeline.run_pipeline)
    return {"status": "started"}
