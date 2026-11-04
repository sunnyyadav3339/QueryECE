"""Crawl -> store pages -> (re)index changed pages -> refresh structured tables.

Incremental: a page is re-chunked and re-embedded only when the hash of its
extracted text changes, so the weekly run costs little when the site is quiet.

Run manually:  python -m app.ingest.pipeline
"""

import hashlib
import logging
import re
import threading
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from app.db.database import SessionLocal, init_db
from app.db.models import Chunk, Course, CrawlRun, Faculty, Opportunity, Page, Project, Startup, Update
from app.ingest.photos import sync_photos
from app.ingest import extractors
from app.ingest.crawler import (
    HOST, RESUME_HOST, USER_AGENT, FetchedPage, crawl, fetch_bytes, in_ece_scope, page_category,
)
from app.ingest.course_structure import ACAD_HOST, CATEGORY as STRUCTURE_CATEGORY, COURSE_STRUCTURES_PAGE
from app.ingest.html_text import html_to_text, pdf_to_text
from app.ingest.privacy import redact_applicant_lists
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


def _changed_lines(old: str, new: str, limit: int = 4) -> str:
    """The substantive lines that appear in the new text but not the old one."""
    before = set((old or "").splitlines())
    added = [ln.strip() for ln in new.splitlines() if ln.strip() not in before and len(ln.strip()) > 25]
    return "\n".join(added[:limit])[:600]


def _store_page(db, fetched: FetchedPage, category: str | None = None, record: bool = False) -> tuple[Page, bool]:
    """Upsert a page; re-index it if its text changed. Returns (page, changed).

    With record=True, a new or changed page is also logged to the "What's new" feed.
    """
    # Every page passes through here, so this is where named applicant lists are cut.
    fetched.text = redact_applicant_lists(fetched.text)
    digest = hashlib.sha256(fetched.text.encode()).hexdigest()
    page = db.query(Page).filter_by(url=fetched.url).first()
    is_new = page is None
    if page is None:
        page = Page(url=fetched.url)
        db.add(page)
    retitled = page.title != fetched.title  # titles are part of every indexed chunk
    page.title = fetched.title
    page.category = category or page_category(fetched.url)
    page.fetched_at = _now()
    was_active, page.active = page.active, True
    changed = page.content_hash != digest or was_active is False or retitled
    if not changed:
        return page, False

    if record:
        detail = fetched.text[:300] if is_new else _changed_lines(page.text, fetched.text)
        if is_new or detail:  # skip pure markup/whitespace changes
            db.add(Update(kind="new_page" if is_new else "updated_page", title=fetched.title or fetched.url,
                          url=fetched.url, detail=detail))
    page.text = fetched.text
    page.content_hash = digest
    page.changed_at = _now()
    db.flush()  # assigns page.id

    index.delete_page_chunks(db, page.id)
    db.query(Chunk).filter_by(page_id=page.id).delete()
    if page.category == STRUCTURE_CATEGORY:
        # Other departments' structures would crowd ECE's pages out of search;
        # find_course_structure reads page.text directly.
        return page, True
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


def _refresh_courses(db, records):
    """Replace the course table. The same code can appear in several PDFs: keep the fullest form."""
    if not records:
        return
    best: dict[str, dict] = {}
    for rec in records:
        current = best.get(rec["code"])
        if current is None or len(rec["contents"] or "") > len(current["contents"] or ""):
            best[rec["code"]] = rec
    db.query(Course).delete()
    db.add_all(Course(**rec) for rec in best.values())


def _store_faculty_sites(db, seen_urls: set[str]) -> int:
    """Personal pages listed in faculty profiles, where publication lists usually live.

    Only the page itself is read, and failures are fine: many are unreachable from
    outside the campus or simply out of date.
    """
    stored = 0
    db.flush()
    for fac in db.query(Faculty).all():
        profile = db.query(Page).filter_by(url=fac.profile_url).first() if fac.profile_url else None
        # The resume link comes first on profiles that have one; the website follows it.
        urls = [u.rstrip(").,") for u in re.findall(r"https?://\S+", (profile.text or "")[:600])] if profile else []
        url = next((u for u in urls if RESUME_HOST not in u), "")
        if not url or url in seen_urls or in_ece_scope(url):
            continue
        fac.website = url
        try:
            resp = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=15, follow_redirects=True)
            if resp.status_code >= 400 or "html" not in resp.headers.get("content-type", ""):
                continue
            _title, text, _soup = html_to_text(resp.text, url)
        except (httpx.HTTPError, ValueError) as exc:
            log.info("faculty site unavailable %s: %s", url, exc)
            continue
        if len(text) < 200:
            continue
        seen_urls.add(url)
        _store_page(db, FetchedPage(url=url, title=f"Personal page: Prof. {fac.name}", text=text),
                    category="faculty_profile")
        stored += 1
    return stored


def _refresh_projects(db, records, record: bool = False):
    if not records:
        return
    resolver = _resolver(db)
    known = {t for (t,) in db.query(Project.title)}
    db.query(Project).delete()  # the source table is the full list; replace wholesale
    for rec in records:
        fid = resolver.resolve(rec["faculty_raw"] or "")
        db.add(Project(**rec, faculty_id=fid))
        if record and rec["title"] not in known:
            db.add(Update(kind="new_project", title=rec["title"][:300], faculty_id=fid,
                          detail=f"{rec.get('faculty_raw') or ''} · {rec.get('agency') or ''} · {rec.get('year') or ''}"))


def _refresh_startups(db, records):
    if not records:
        return
    resolver = _resolver(db)
    db.query(Startup).delete()
    for rec in records:
        db.add(Startup(**rec, faculty_id=resolver.resolve(rec["founder_raw"] or "")))


def _refresh_opportunities(db, records, record: bool = False):
    if not records:
        return
    seen = set()
    for rec in records:
        seen.add(rec["url"])
        opp = db.query(Opportunity).filter_by(url=rec["url"]).first()
        if opp is None:
            opp = Opportunity(**rec)
            db.add(opp)
            if record:
                db.add(Update(kind="new_opening", title=rec["title"][:300], url=rec["url"],
                              detail=" · ".join(x for x in (rec.get("kind"), rec.get("department"), rec.get("deadline")) if x)))
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


def run_pipeline(max_pages: int | None = None, feed: bool = True) -> dict:
    """Crawl and re-index. feed=False skips the What's new log (for a crawl that changes
    how pages are read, where everything would otherwise look "updated")."""
    if not _run_lock.acquire(blocking=False):
        return {"status": "already_running"}
    init_db()
    db = SessionLocal()
    run = CrawlRun()
    db.add(run)
    db.commit()
    try:
        seen_urls: set[str] = set()
        # The first crawl would log every page as "new"; only record changes after that.
        record = feed and db.query(CrawlRun).filter_by(status="ok").count() > 0
        structured = {"faculty": [], "projects": [], "startups": [], "opportunities": [], "courses": []}
        resumes: dict[int, str] = {}  # faculty id -> resume URL, "" when the profile has none
        kwargs = {"max_pages": max_pages} if max_pages else {}
        for fetched in crawl(**kwargs):
            seen_urls.add(fetched.url)
            _page, changed = _store_page(db, fetched, record=record)
            run.pages_fetched += 1
            run.pages_changed += int(changed)
            # Not other programmes' structures: their rows would mix into ECE's term listings.
            if (fetched.is_pdf and page_category(fetched.url) != STRUCTURE_CATEGORY
                    and re.search(r"Subject\s*Code|Course\s*Title", fetched.text)):
                structured["courses"] += extractors.extract_courses(fetched.text, fetched.url, fetched.title)
            if fetched.soup is not None:
                if fetched.url.endswith(FACULTY_DIR):
                    structured["faculty"] = extractors.extract_faculty_directory(fetched.soup, fetched.url)
                elif fetched.url.endswith(PROJECTS):
                    structured["projects"] = extractors.extract_projects(fetched.soup)
                elif fetched.url.endswith(STARTUPS):
                    structured["startups"] = extractors.extract_startups(fetched.soup)
                elif CAREERS in fetched.url:
                    structured["opportunities"] += extractors.extract_opportunities(fetched.soup, fetched.url)
                elif page_category(fetched.url) == "faculty_profile":
                    found = extractors.extract_profile_resume(fetched.soup, fetched.url)
                    if found is not None:
                        resumes[found[0]] = found[1]
            if run.pages_fetched % 25 == 0:
                db.commit()
                log.info("crawl progress: %s fetched, %s changed", run.pages_fetched, run.pages_changed)

        _refresh_faculty(db, structured["faculty"])
        # Only profiles fetched in this run are updated, so one failed fetch can't erase a resume.
        for fid, resume_url in resumes.items():
            if (fac := db.get(Faculty, fid)) is not None:
                fac.resume_url = resume_url
        db.flush()
        try:
            photos = sync_photos(db.query(Faculty).all())
        except Exception:  # photos are cosmetic; never fail the crawl over them
            log.exception("photo sync failed")
            photos = {"error": True}
        _refresh_projects(db, structured["projects"], record)
        _refresh_startups(db, structured["startups"])
        _refresh_opportunities(db, structured["opportunities"], record)
        _refresh_courses(db, structured["courses"])
        db.flush()
        faculty_sites = _store_faculty_sites(db, seen_urls)

        # Retire pages that disappeared from the site. Skip on a suspiciously
        # small crawl (site outage) so a bad run can't wipe the index.
        if run.pages_fetched >= 20 and not max_pages:
            opp_urls = {o.url for o in db.query(Opportunity.url).filter(Opportunity.active.is_(True))}
            for page in db.query(Page).filter(Page.active.is_(True)).all():
                # Only retire our own site's pages: channeli and personal sites are
                # often unreachable from here, which doesn't mean they're gone.
                host = urlsplit(page.url).netloc
                # Course structures are retired only when their index page was read this run.
                ours = host == HOST or (host == ACAD_HOST and COURSE_STRUCTURES_PAGE in seen_urls)
                if page.url not in seen_urls and page.url not in opp_urls and ours:
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
            "photos": photos, "courses": db.query(Course).count(), "faculty_sites": faculty_sites,
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
    parser.add_argument("--no-feed", action="store_true", help="don't log this crawl's changes to What's new")
    args = parser.parse_args()
    print(json.dumps(run_pipeline(args.max_pages, feed=not args.no_feed), indent=2))
