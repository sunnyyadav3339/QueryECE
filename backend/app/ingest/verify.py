"""Check the knowledge base against the live website.

    python -m app.ingest.verify

Re-downloads every stored page, extracts it the same way the crawler does, and
compares the result with what's stored. Differences mean the site changed since
the last crawl, or that a page is being read inconsistently. Read-only.
"""

import collections
import hashlib
import sys
import time
from urllib.parse import unquote, urlsplit

import httpx

from app.db.database import SessionLocal
from app.db.models import Course, Faculty, Page, Project
from app.ingest.crawler import USER_AGENT, is_pdf
from app.ingest.html_text import html_to_text
from app.ingest.ocr import extract_pdf

SCANNED_TAG = "[scanned copy]"


def short(url: str) -> str:
    return unquote(url).split("Department/")[-1].replace("https://iitr.ac.in/", "~/")[:90]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=httpx.Timeout(90, connect=8), follow_redirects=True)
    ok, changed, unreachable = 0, [], []
    with SessionLocal() as db:
        pages = db.query(Page).filter(Page.active.is_(True)).all()
        by_cat = collections.Counter(p.category for p in pages)
        chars = sum(len(p.text or "") for p in pages)
        for page in pages:
            try:
                resp = client.get(page.url)
                if resp.status_code >= 400:
                    unreachable.append((resp.status_code, page.url))
                    continue
                text = extract_pdf(resp.content)[0] if is_pdf(page.url) else html_to_text(resp.text, page.url)[1]
            except Exception as exc:
                unreachable.append((type(exc).__name__, page.url))
                continue
            finally:
                time.sleep(0.1)
            if hashlib.sha256(text.encode()).hexdigest() == page.content_hash:
                ok += 1
            else:
                changed.append(page.url)

        print(f"Pages stored: {len(pages)} ({chars:,} characters) by section: {dict(by_cat)}")
        print(f"Faculty: {db.query(Faculty).count()} | sponsored projects: {db.query(Project).count()} | "
              f"courses: {db.query(Course).count()}")
        scanned = [p for p in pages if SCANNED_TAG in (p.title or "")]
        print(f"\nRead by OCR ({len(scanned)}):")
        for p in scanned:
            print(f"  {len(p.text):>7,} chars  {short(p.url)}")
        thin = [p for p in pages if len(p.text or "") < 150]
        print(f"\nAlmost no text ({len(thin)}), usually image-only pages:")
        for p in thin:
            print(f"  {len(p.text or ''):>5} chars  {short(p.url)}")

    print(f"\nCompared with the live site: {ok} identical, {len(changed)} different, {len(unreachable)} unreachable")
    for url in changed:
        print(f"  DIFFERENT    {short(url)}")
    hosts = collections.Counter(urlsplit(u).netloc for _, u in unreachable)
    if unreachable:
        print(f"  unreachable by host: {dict(hosts)}")
    return 1 if changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
