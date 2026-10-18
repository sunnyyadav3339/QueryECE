"""Crawl -> store pages -> (re)index changed pages -> refresh structured tables.

Incremental: a page is re-chunked and re-embedded only when the hash of its
extracted text changes, so the weekly run costs little when the site is quiet.

Run manually:  python -m app.ingest.pipeline
"""

import hashlib
import logging
import threading
from datetime import datetime, timezone

from app.db.database import SessionLocal, init_db
from app.db.models import Chunk, CrawlRun, Faculty, Opportunity, Page, Project, Startup
from app.ingest.photos import sync_photos
from app.ingest import extractors
from app.ingest.crawler import FetchedPage, crawl, fetch_bytes, page_category
from app.ingest.html_text import pdf_to_text
from app.rag import index
from app.rag.chunker import chunk_page

log = logging.getLogger(__name__)
_run_lock = threading.Lock()

# Pages whose layout we parse into structured tables.
FACULTY_DIR = "People/Faculty/FACULTY%20MEMBERS.html"
PROJECTS = "Research/List%20of%20Sponsored%20Projects.html"
STARTUPS = "Research/Faculty%20Led%20Startups.html"
CAREERS = "/Careers/"


def _now():
    return datetime.now(timezone.utc)


def _store_page(db, fetched: FetchedPage, category: str | None = None) -> tuple[Page, bool]:
    """Upsert a page; re-index it if its text changed. Returns (page, changed)."""
    digest = hashlib.sha256(fetched.text.encode()).hexdigest()
    page = db.query(Page).filter_by(url=fetched.url).first()
    if page is None:
        page = Page(url=fetched.url)
        db.add(page)
    page.title = fetched.title
    page.category = category or page_category(fetched.url)
    page.fetched_at = _now()
    was_active, page.active = page.active, True
    changed = page.content_hash != digest or was_active is False
    if not changed:
        return page, False

    page.text = fetched.text
    page.content_hash = digest
    page.changed_at = _now()
    db.flush()  # assigns page.id

    index.delete_page_chunks(db, page.id)
    db.query(Chunk).filter_by(page_id=page.id).delete()
    rows = []
    for i, ch in enumerate(chunk_page(page.title, page.text)):
        cid = f"{page.id}:{i}"
        db.add(Chunk(id=cid, page_id=page.id, ord=i, heading=ch.heading, text=ch.text))
        rows.append({"id": cid, "text": ch.full_text, "title": page.title, "heading": ch.heading,
                     "body": ch.text, "url": page.url, "category": page.category, "page_id": page.id})
    db.flush()
    index.index_chunks(db, rows)
    return page, True


def _refresh_faculty(db, records):
    if not records:
        return
    for rec in records:
        fac = db.get(Faculty, rec["id"]) or Faculty(id=rec["id"])
        for key, value in rec.items():
            if value is not None or key == "id":
                setattr(fac, key, value)
        db.add(fac)
    db.flush()


def _resolver(db):
    return extractors.FacultyResolver([(f.id, f.name) for f in db.query(Faculty).all()])


def _refresh_projects(db, records):
    if not records:
        return
    resolver = _resolver(db)
    db.query(Project).delete()  # the source table is the full list; replace wholesale
    for rec in records:
        db.add(Project(**rec, faculty_id=resolver.resolve(rec["faculty_raw"] or "")))


def _refresh_startups(db, records):
    if not records:
        return
    resolver = _resolver(db)
    db.query(Startup).delete()
    for rec in records:
        db.add(Startup(**rec, faculty_id=resolver.resolve(rec["founder_raw"] or "")))


def _refresh_opportunities(db, records):
    if not records:
        return
    seen = set()
    for rec in records:
        seen.add(rec["url"])
        opp = db.query(Opportunity).filter_by(url=rec["url"]).first()
        if opp is None:
            opp = Opportunity(**rec)
            db.add(opp)
        else:
            for key, value in rec.items():
                setattr(opp, key, value)
        opp.active = True
        # Pull the advert PDF for ECE openings so the assistant can answer
        # eligibility / stipend / how-to-apply questions.
        if opp.is_ece and not opp.details and rec["url"].lower().endswith(".pdf"):
            data = fetch_bytes(rec["url"])
            if data:
                try:
                    opp.details = pdf_to_text(data)[:20000]
                except Exception as exc:
                    log.warning("advert parse failed %s: %s", rec["url"], exc)
            if opp.details:
                _store_page(db, FetchedPage(url=rec["url"], title=rec["title"][:200], text=opp.details,
                                            is_pdf=True), category="opportunities")
    for opp in db.query(Opportunity).filter(Opportunity.active.is_(True)).all():
        if opp.url not in seen:
            opp.active = False


def run_pipeline(max_pages: int | None = None) -> dict:
    if not _run_lock.acquire(blocking=False):
        return {"status": "already_running"}
    init_db()
    db = SessionLocal()
    run = CrawlRun()
    db.add(run)
    db.commit()
    try:
        seen_urls: set[str] = set()
        structured = {"faculty": [], "projects": [], "startups": [], "opportunities": []}
        kwargs = {"max_pages": max_pages} if max_pages else {}
        for fetched in crawl(**kwargs):
            seen_urls.add(fetched.url)
            _page, changed = _store_page(db, fetched)
            run.pages_fetched += 1
            run.pages_changed += int(changed)
            if fetched.soup is not None:
                if fetched.url.endswith(FACULTY_DIR):
                    structured["faculty"] = extractors.extract_faculty_directory(fetched.soup, fetched.url)
                elif fetched.url.endswith(PROJECTS):
                    structured["projects"] = extractors.extract_projects(fetched.soup)
                elif fetched.url.endswith(STARTUPS):
                    structured["startups"] = extractors.extract_startups(fetched.soup)
                elif CAREERS in fetched.url:
                    structured["opportunities"] += extractors.extract_opportunities(fetched.soup, fetched.url)
            if run.pages_fetched % 25 == 0:
                db.commit()
                log.info("crawl progress: %s fetched, %s changed", run.pages_fetched, run.pages_changed)

        _refresh_faculty(db, structured["faculty"])
        db.flush()
        try:
            photos = sync_photos(db.query(Faculty).all())
        except Exception:  # photos are cosmetic; never fail the crawl over them
            log.exception("photo sync failed")
            photos = {"error": True}
        _refresh_projects(db, structured["projects"])
        _refresh_startups(db, structured["startups"])
        _refresh_opportunities(db, structured["opportunities"])

        # Retire pages that disappeared from the site. Skip on a suspiciously
        # small crawl (site outage) so a bad run can't wipe the index.
        if run.pages_fetched >= 20 and not max_pages:
            opp_urls = {o.url for o in db.query(Opportunity.url).filter(Opportunity.active.is_(True))}
            for page in db.query(Page).filter(Page.active.is_(True)).all():
                if page.url not in seen_urls and page.url not in opp_urls:
                    page.active = False
                    index.delete_page_chunks(db, page.id)
                    db.query(Chunk).filter_by(page_id=page.id).delete()
                    run.pages_removed += 1

        run.status = "ok"
        run.finished_at = _now()
        db.commit()
        summary = {
            "status": "ok", "pages_fetched": run.pages_fetched, "pages_changed": run.pages_changed,
            "pages_removed": run.pages_removed, "faculty": len(structured["faculty"]),
            "projects": len(structured["projects"]), "startups": len(structured["startups"]),
            "opportunities": len(structured["opportunities"]), "chunks_indexed": index.count(),
            "photos": photos,
        }
        log.info("pipeline finished: %s", summary)
        return summary
    except Exception as exc:
        db.rollback()
        run = db.merge(run)
        run.status, run.error, run.finished_at = "failed", repr(exc)[:2000], _now()
        db.commit()
        log.exception("pipeline failed")
        raise
    finally:
        db.close()
        _run_lock.release()


def is_running() -> bool:
    return _run_lock.locked()


if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=None, help="limit for a quick test crawl")
    args = parser.parse_args()
    print(json.dumps(run_pipeline(args.max_pages), indent=2))
