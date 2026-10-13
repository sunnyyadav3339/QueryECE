"""Breadth-first crawler for the IIT Roorkee ECE department site.

Scope: every HTML page under the ECE department path (discovered through the
site menu and in-page links), PDFs linked from those pages, and a fixed set of
institute career pages that list RA/JRF/post-doc adverts.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from app.config import CRAWL_DELAY_SECONDS, CRAWL_MAX_PAGES
from app.ingest.html_text import html_to_text, pdf_to_text

log = logging.getLogger(__name__)

HOST = "iitr.ac.in"
ECE_PATH = "/Departments/Electronics%20and%20Communication%20Engineering%20Department/"
ECE_BASE = f"https://{HOST}{ECE_PATH}"

SEED_PATHS = [
    "Home.html",
    "About%20Us/About%20the%20Department.html",
    "About%20Us/Contact%20Us.html",
    "About%20Us/Guest%20Faculty.html",
    "People/Faculty/FACULTY%20MEMBERS.html",
    "Research/Research%20Groups.html",
    "Research/List%20of%20Sponsored%20Projects.html",
    "Research/Faculty%20Led%20Startups.html",
    "Research/Patent.html",
]
# Institute pages outside the ECE path that students ask about. Their links
# are not followed.
EXTRA_PAGES = [
    f"https://{HOST}/Careers/Project%20Jobs.html",
    f"https://{HOST}/Careers/Other%20job%20openings/Post%20Doctoral%20Fellowship%20Position.html",
    f"https://{HOST}/Academics/Academic%20Calendar.html",
]
MAX_PDFS = 60
MAX_PDF_BYTES = 4 * 1024 * 1024
USER_AGENT = "QueryECE-bot/1.0 (student project; IIT Roorkee ECE assistant)"


@dataclass
class FetchedPage:
    url: str
    title: str
    text: str
    is_pdf: bool = False
    soup: BeautifulSoup | None = None


def normalize(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    path = quote(unquote(parts.path), safe="/-._~!$&'()*+,;=:@")
    return urlunsplit((parts.scheme or "https", host, path, parts.query, ""))


def in_ece_scope(url: str) -> bool:
    parts = urlsplit(url)
    return parts.netloc == HOST and parts.path.startswith(ECE_PATH)


def is_pdf(url: str) -> bool:
    return urlsplit(url).path.lower().endswith(".pdf")


def is_html(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return path.endswith((".html", ".htm", "/")) or "." not in path.rsplit("/", 1)[-1]


def page_category(url: str) -> str:
    path = unquote(urlsplit(url).path).lower()
    if "/careers/" in path:
        return "opportunities"
    if "/people/faculty/" in path and path.rsplit("/", 1)[-1][:1].isdigit():
        return "faculty_profile"
    for key, category in (
        ("/people/", "people"), ("/research/", "research"), ("/academics/", "academics"),
        ("/about us/", "about"), ("/placement", "placements"),
    ):
        if key in path:
            return category
    return "pdf" if path.endswith(".pdf") else "general"


def _links(soup: BeautifulSoup, base: str) -> list[str]:
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        out.append(normalize(urljoin(base, href)))
    return out


def crawl(max_pages: int = CRAWL_MAX_PAGES):
    """Yield FetchedPage objects. Errors on individual pages are logged and skipped."""
    queue = deque(normalize(ECE_BASE + p) for p in SEED_PATHS)
    queue.extend(normalize(u) for u in EXTRA_PAGES)
    seen = set(queue)
    pdf_count = 0
    fetched = 0

    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True
    ) as client:
        while queue and fetched < max_pages:
            url = queue.popleft()
            try:
                resp = client.get(url)
            except httpx.HTTPError as exc:
                log.warning("fetch failed %s: %s", url, exc)
                continue
            finally:
                time.sleep(CRAWL_DELAY_SECONDS)
            if resp.status_code >= 400:
                log.info("HTTP %s %s", resp.status_code, url)
                continue
            fetched += 1
            ctype = resp.headers.get("content-type", "")

            if "pdf" in ctype or is_pdf(url):
                if len(resp.content) > MAX_PDF_BYTES:
                    continue
                try:
                    text = pdf_to_text(resp.content)
                except Exception as exc:
                    log.warning("pdf parse failed %s: %s", url, exc)
                    continue
                if text.strip():
                    name = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
                    yield FetchedPage(url=url, title=name, text=text, is_pdf=True)
                continue

            title, text, soup = html_to_text(resp.text, url)
            yield FetchedPage(url=url, title=title, text=text, soup=soup)

            # Extra pages are institute-wide (career adverts are handled by the
            # opportunities extractor), so don't expand their links here.
            if not in_ece_scope(url):
                continue
            for link in _links(soup, url):
                if link in seen or urlsplit(link).netloc != HOST:
                    continue
                if in_ece_scope(link) and is_html(link):
                    seen.add(link)
                    queue.append(link)
                elif is_pdf(link) and pdf_count < MAX_PDFS:
                    seen.add(link)
                    pdf_count += 1
                    queue.append(link)


def fetch_bytes(url: str) -> bytes | None:
    """One-off fetch used for advert PDFs."""
    try:
        resp = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)
        if resp.status_code < 400 and len(resp.content) <= MAX_PDF_BYTES:
            return resp.content
    except httpx.HTTPError as exc:
        log.warning("fetch failed %s: %s", url, exc)
    return None
