"""Breadth-first crawler for the IIT Roorkee ECE department site.

Scope:
- every HTML page under the ECE department path, found through the site menu,
  in-page links and the site's own sitemap.txt
- PDFs linked from those pages, read in full (scanned ones through OCR)
- faculty resumes on channeli.in, when reachable (campus network only)
- institute academic pages students ask about (calendar, regulations, exams,
  fees, admissions, scholarships...) and the PDFs they link to
- institute career pages that list RA/JRF/post-doc adverts
"""

import logging
import re
import time
from collections import deque
from dataclasses import dataclass
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from app.config import CRAWL_DELAY_SECONDS, CRAWL_MAX_PAGES
from app.ingest.html_text import ONCLICK_URL, clean, docx_to_text, html_to_text
from app.ingest.ocr import extract_pdf

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
]
# Institute academic pages; their PDFs are followed too, their other links aren't.
ACADEMIC_PAGES = [
    f"https://{HOST}/Academics/{quote(name)}.html" for name in (
        "Electronics and Communication Engineering", "Academic Calendar", "Academic Calendar Autumn Semester",
        "Academic Calendar Spring Semester", "Time Table", "Exam Schedule", "Academic Regulations",
        "Academic Information", "Academic Programmes", "Policies", "Guidelines", "Institute Fees",
        "ScholarshipsAwards", "PMRF", "Committees", "People", "Contact", "Downloads", "FAQs",
        "Frequently Asked Questions (FAQs)", "VerificationTranscriptsCertificates", "Admission",
        "Admission To Undergraduate Programmes", "Admission To Postgraduate Programmes",
        "Admission To M.Tech.M.Arch.M.U.R.P. Programmes", "Admission To Doctoral Programmes",
        "Admission to M.Tech. (VLSI) for Industry Professionals", "Ph.D. Programmes", "Postgraduate Programmes",
        "Notifications", "General Notifications", "Notifications Related to Ph.D. Programmes",
        "Notifications Related to Postgraduate Programmes",
    )
]
SITEMAP_URL = f"https://{HOST}/sitemap.txt"
# Resumes linked from faculty profiles; only reachable from the IITR network.
RESUME_HOST = "channeli.in"
MAX_ECE_PDFS = 200
MAX_INSTITUTE_PDFS = 120
MAX_PDF_BYTES = 40 * 1024 * 1024  # one scanned time table is 24 MB
USER_AGENT = "QueryECE-bot/1.0 (student project; IIT Roorkee ECE assistant)"


@dataclass
class FetchedPage:
    url: str
    title: str
    text: str
    is_pdf: bool = False
    soup: BeautifulSoup | None = None
    source_scanned: bool = False  # text came from OCR


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


def is_docx_resume(url: str) -> bool:
    parts = urlsplit(url)
    return parts.netloc == RESUME_HOST and parts.path.lower().endswith(".docx")


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


def _links(soup: BeautifulSoup, base: str) -> list[tuple[str, str]]:
    """(url, link text) for every usable link on a page."""
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        out.append((normalize(urljoin(base, href)), clean(a.get_text(" "))))
    for el in soup.find_all(attrs={"onclick": True}):
        match = ONCLICK_URL.search(el["onclick"])
        if match:
            out.append((normalize(urljoin(base, match.group(1))), clean(el.get_text(" "))))
    return out


def _sitemap_seeds(client: httpx.Client) -> list[str]:
    """ECE pages listed in the site's sitemap, which may not be linked from any menu.

    Faculty pages are excluded: the sitemap also lists stale profiles of people no
    longer in the department. The directory page links the current ones.
    """
    try:
        resp = client.get(SITEMAP_URL)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("sitemap unavailable: %s", exc)
        return []
    urls = (normalize(line.strip()) for line in resp.text.splitlines() if line.strip().startswith("http"))
    return [u for u in urls if in_ece_scope(u) and is_html(u) and "/People/Faculty/" not in unquote(u)]


# Institute pages link hundreds of documents; most don't concern ECE students.
# Candidate lists also name individuals, so they stay out regardless of relevance.
INSTITUTE_SKIP = re.compile(
    r"list of|list &|enrol+ment|shortlist|selected candidates|round[ _-]?\d|(first|second|third|fourth|fifth) round|"
    r"sample[ _]offer|annexure|performa|proforma|affidavit",
    re.I,
)
OTHER_PROGRAMMES = re.compile(r"\b(mba|mim|m\.?\s?sc|b\.?\s?des|m\.?\s?des|b\.?\s?arch|m\.?\s?arch|murp|m\.?u\.?r\.?p)\b", re.I)
COVERS_ECE_TOO = re.compile(r"m\.?\s?tech|other than|all programs?", re.I)
# These name individual applicants, on any site.
APPLICANT_LIST = re.compile(r"shortlist|selected\b.*\bcandidates|wait\s?-?list|merit[\s_-]?list|complete_merit", re.I)
YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
OLDEST_DOCUMENT_YEAR = 2024  # older calendars and fee notices would just compete with current ones
OLDEST_REGULATION_YEAR = 2016  # batches admitted under these are still enrolled


def wanted_institute_pdf(url: str, label: str) -> bool:
    name = f"{label} {unquote(urlsplit(url).path.rsplit('/', 1)[-1])}"
    if INSTITUTE_SKIP.search(name):
        return False
    # "M.Tech./M.Arch./M.U.R.P" or "All Programs (Other than MBA)" still concern ECE students.
    if OTHER_PROGRAMMES.search(name) and not COVERS_ECE_TOO.search(name):
        return False
    years = [int(y) for y in YEAR.findall(name)]
    if not years:
        return True
    oldest = OLDEST_REGULATION_YEAR if re.search(r"ordinance|regulation", name, re.I) else OLDEST_DOCUMENT_YEAR
    return max(years) >= oldest


GENERIC_LABELS = re.compile(r"^(view|view pdf|download|click here|here|link|pdf|read more)?$", re.I)


def _pdf_title(url: str, label: str, source_title: str) -> str:
    """A searchable title: what the page calls the document, plus its file name."""
    name = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    if urlsplit(url).netloc == RESUME_HOST:
        return f"Resume / CV: {source_title}"
    return f"{label} ({name})" if label and not GENERIC_LABELS.match(label) else name


def crawl(max_pages: int = CRAWL_MAX_PAGES):
    """Yield FetchedPage objects. Errors on individual pages are logged and skipped."""
    academic = {normalize(u) for u in ACADEMIC_PAGES}
    pdf_titles: dict[str, str] = {}
    ece_pdfs = institute_pdfs = 0
    fetched = 0
    resume_host_down = False

    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=httpx.Timeout(60, connect=8), follow_redirects=True
    ) as client:
        seeds = [normalize(ECE_BASE + p) for p in SEED_PATHS]
        seeds += _sitemap_seeds(client)
        seeds += [normalize(u) for u in EXTRA_PAGES]
        seeds += sorted(academic)
        queue = deque(dict.fromkeys(seeds))
        seen = set(queue)
        while queue and fetched < max_pages:
            url = queue.popleft()
            is_resume = urlsplit(url).netloc == RESUME_HOST
            if is_resume and resume_host_down:
                continue
            try:
                resp = client.get(url)
            except httpx.HTTPError as exc:
                log.warning("fetch failed %s: %s", url, exc)
                if is_resume and isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
                    resume_host_down = True  # off campus: don't wait on every resume
                continue
            finally:
                time.sleep(CRAWL_DELAY_SECONDS)
            if resp.status_code >= 400:
                log.info("HTTP %s %s", resp.status_code, url)
                continue
            fetched += 1
            ctype = resp.headers.get("content-type", "")

            if is_docx_resume(url):  # a few faculty upload their resume as Word
                try:
                    text = docx_to_text(resp.content)
                except Exception as exc:
                    log.warning("docx parse failed %s: %s", url, exc)
                    continue
                if text.strip():
                    yield FetchedPage(url=url, title=pdf_titles.get(url, url), text=text, is_pdf=True)
                continue

            if "pdf" in ctype or is_pdf(url):
                if len(resp.content) > MAX_PDF_BYTES:
                    log.warning("skipping oversized pdf (%d MB): %s", len(resp.content) >> 20, url)
                    continue
                try:
                    text, used_ocr = extract_pdf(resp.content)
                except Exception as exc:
                    log.warning("pdf parse failed %s: %s", url, exc)
                    continue
                if text.strip():
                    name = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
                    title = pdf_titles.get(url, name)
                    yield FetchedPage(url=url, title=f"{title} [scanned copy]" if used_ocr else title,
                                      text=text, is_pdf=True, source_scanned=used_ocr)
                continue

            title, text, soup = html_to_text(resp.text, url)
            yield FetchedPage(url=url, title=title, text=text, soup=soup)

            # Career pages are handled by the opportunities extractor, and academic
            # pages only contribute their PDFs: the rest of the site isn't in scope.
            in_ece = in_ece_scope(url)
            if not in_ece and url not in academic:
                continue
            for link, label in _links(soup, url):
                if link in seen:
                    continue
                host = urlsplit(link).netloc
                if in_ece and host == HOST and in_ece_scope(link) and is_html(link):
                    seen.add(link)
                    queue.append(link)
                elif not (is_pdf(link) or is_docx_resume(link)):
                    continue
                elif APPLICANT_LIST.search(f"{label} {unquote(urlsplit(link).path)}"):
                    continue
                elif in_ece and host in (HOST, RESUME_HOST) and ece_pdfs < MAX_ECE_PDFS:
                    ece_pdfs += 1
                    seen.add(link)
                    pdf_titles[link] = _pdf_title(link, label, title)
                    queue.append(link)
                elif (not in_ece and host == HOST and institute_pdfs < MAX_INSTITUTE_PDFS
                      and wanted_institute_pdf(link, label)):
                    institute_pdfs += 1
                    seen.add(link)
                    pdf_titles[link] = _pdf_title(link, label, title)
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
