"""Structured extraction for pages whose layout we know.

These feed the exact-lookup agent tools (faculty directory, sponsored
projects, startups, openings); every page is *also* chunked into the vector
index by the pipeline, so nothing here is the only path to the content.
"""

import re
import unicodedata
from urllib.parse import unquote, urljoin

from bs4 import BeautifulSoup
from rapidfuzz import fuzz, process

from app.ingest.html_text import RESUME_LABEL, clean, is_resume_file

EMAIL_RE = re.compile(r"[\w.+-]+\s*(?:\[at\]|@)\s*[\w-]+(?:\.[\w-]+)+", re.I)
PHONE_RE = re.compile(r"\+?\d[\d\s-]{7,}\d")
PROFILE_ID_RE = re.compile(r"/Faculty/(\d+)\.html", re.I)
HONORIFICS_RE = re.compile(r"\b(?:prof(?:essor)?|dr|mr|ms|mrs)\b\.?", re.I)


# ---------------------------------------------------------------------------
# Name resolution (PI strings -> faculty ids)
# ---------------------------------------------------------------------------


def name_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = HONORIFICS_RE.sub(" ", value)
    value = re.sub(r"[^a-z\s]", " ", value)
    return " ".join(value.split())


class FacultyResolver:
    """Fuzzy-match free-text names ("Prof. R.K. Panigrahi") to faculty ids."""

    def __init__(self, faculty: list[tuple[int, str]]):
        self.keys = {fid: name_key(name) for fid, name in faculty}

    def resolve(self, raw: str, min_score: int = 85) -> int | None:
        query = name_key(raw)
        if not query or not self.keys:
            return None
        # Initials-aware: "r k panigrahi" should match "rajib kumar panigrahi".
        surname = query.split()[-1]
        candidates = {fid: key for fid, key in self.keys.items() if surname in key.split()}
        pool = candidates or self.keys
        best = process.extract(query, pool, scorer=fuzz.token_set_ratio, limit=2)
        if not best:
            return None
        _key, score, fid = best[0]
        if len(candidates) == 1 and score >= 60:
            return fid
        if score < min_score:
            return None
        if len(best) > 1 and best[1][1] == score:
            return None  # ambiguous
        return fid


# ---------------------------------------------------------------------------
# Page-specific extractors
# ---------------------------------------------------------------------------


def extract_faculty_directory(soup: BeautifulSoup, page_url: str) -> list[dict]:
    records = []
    for card in soup.select(".faculty-card"):
        name_el = card.select_one(".name")
        link = card.find("a", href=PROFILE_ID_RE)
        if not name_el or not link:
            continue
        match = PROFILE_ID_RE.search(unquote(link["href"]))
        record = {
            "id": int(match.group(1)),
            "name": clean(name_el.get_text(" ")),
            "designation": clean(card.select_one(".designation").get_text(" "))
            if card.select_one(".designation") else None,
            "email": None, "phone": None, "website": None,
            "interests": clean(card.select_one(".body").get_text(" ")).removesuffix("READ MORE").strip()
            if card.select_one(".body") else None,
            "profile_url": urljoin(page_url, link["href"]).replace(" ", "%20"),
            "image_url": None,
        }
        img = card.find("img", src=True)
        if img and "display_pictures" in img["src"]:
            record["image_url"] = img["src"]
        for info in card.select(".info-content"):
            text = clean(info.get_text(" "))
            if not text:
                continue
            if EMAIL_RE.search(text):
                record["email"] = re.sub(r"\s*\[at\]\s*", "@", EMAIL_RE.search(text).group(0), flags=re.I)
            elif text.startswith("http"):
                record["website"] = text
            elif PHONE_RE.fullmatch(text):
                record["phone"] = text
        records.append(record)
    return records


def extract_profile_resume(soup: BeautifulSoup, page_url: str) -> tuple[int, str] | None:
    """(faculty id, resume PDF URL or "") from a profile page, or None if it has no resume button."""
    match = PROFILE_ID_RE.search(unquote(page_url))
    if not match:
        return None
    for a in soup.find_all("a", href=True):
        if RESUME_LABEL.match(clean(a.get_text(" "))):
            href = urljoin(page_url, a["href"].strip())
            return int(match.group(1)), href if is_resume_file(href) else ""
    return None


def extract_projects(soup: BeautifulSoup) -> list[dict]:
    """List of Sponsored Projects: SI. No. | Faculty | Scheme/Title | Funding Agency | Co-PI | Year."""
    records = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header = [clean(c.get_text(" ")).casefold() for c in rows[0].find_all(["td", "th"])]
        if not any("title" in h for h in header):
            continue

        def col(name):
            return next((i for i, h in enumerate(header) if name in h), None)

        idx = {"faculty": col("faculty"), "title": col("title"), "agency": col("agency"),
               "co_pi": col("co-pi"), "year": col("year")}
        for tr in rows[1:]:
            cells = [clean(c.get_text(" ")) for c in tr.find_all(["td", "th"])]
            get = lambda key: cells[idx[key]] if idx[key] is not None and idx[key] < len(cells) else None  # noqa: E731
            if not get("title"):
                continue
            records.append({
                "faculty_raw": get("faculty"), "title": get("title"), "agency": get("agency"),
                "co_pi": get("co_pi") or None, "year": get("year"),
            })
    return records


def extract_startups(soup: BeautifulSoup) -> list[dict]:
    records = []
    for desc in soup.select(".description"):
        strong = desc.find("strong")
        if not strong:
            continue
        lines = [clean(t) for t in desc.get_text("\n").split("\n")]
        lines = [line for line in lines if line]
        founder = None
        for i, line in enumerate(lines):
            if re.search(r"founder|director|promoter", line, re.I):
                after = line.split(":", 1)[1].strip() if ":" in line else ""
                founder = after or (lines[i + 1] if i + 1 < len(lines) else None)
                break
        website = re.search(r"https?://\S+", desc.get_text(" "))
        records.append({
            "name": clean(strong.get_text(" ")),
            "founder_raw": founder,
            "website": website.group(0) if website else None,
            "description": " ".join(lines[1:])[:3000],
        })
    return records


DEPT_RE = re.compile(r"(?:Dept\.?|Department)\s+of\s+([^:(]+?)\s*(?:[:(]|$)")
UNIT_RE = re.compile(r"in\s+([A-Z][A-Za-z&.\s]+?)\s*(?:[:(]|$)")  # "...Project Fellow in ICED (..."
ECE_RE = re.compile(r"electronics|\bE\.?C\.?E\b|communication engg", re.I)
DATE_RE = re.compile(r"dated:?\s*([A-Za-z]+\s+\d{1,2},\s*\d{4}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})", re.I)
DEADLINE_RE = re.compile(r"\((?:last date[^:]*|date and time for walk-in interview)\s*:\s*([^)]+)\)", re.I)


def extract_opportunities(soup: BeautifulSoup, page_url: str) -> list[dict]:
    kind = "Post-Doctoral Fellowship" if "Post%20Doctoral" in page_url else "Project Job"
    records = []
    for item in soup.select(".publicationListItem"):
        link = item.find("a", href=True)
        text = clean(item.get_text(" "))
        if not link or not text:
            continue
        text = re.sub(r"\s*\bview\b\s*$", "", text, flags=re.I).removeprefix("View ").strip()
        dept_match = DEPT_RE.search(text) or UNIT_RE.search(text)
        department = clean(dept_match.group(1)) if dept_match else None
        posted = DATE_RE.search(text)
        deadline = DEADLINE_RE.search(text)
        records.append({
            "url": urljoin(page_url, link["href"]).replace(" ", "%20"),
            "kind": kind,
            "title": text,
            "department": department,
            "is_ece": bool(ECE_RE.search(text)),
            "posted_on": posted.group(1) if posted else None,
            "deadline": clean(deadline.group(1)) if deadline else None,
        })
    return records



# Syllabus PDFs use one institute-wide form per course:
#   1. Subject Code: ECN-342 Course Title: RF and Mixed Signals Circuits
#   2. Contact Hours: L: 3 T: 1 P: 0
#   5. Credits: 4 6. Semester : Spring 7. Subject Area: DCC
#   8. Pre-requisite: ...  9. Objective: ...  10. Details of the Course: ...
# OCRed pages vary: "SubjectCode:ECN-357 | CourseTitle:ElectronicSub-Systems", "Subject Code : . EC-343".
_COURSE_START = re.compile(
    r"Subject\s*Code\s*:?[\s.|]*([A-Z]{2,4})\s*-?\s*(\d{3}[A-Z]?)[\s|]*Course\s*Title\s*:?[\s|]*(.+)", re.I)


def _spaced(title: str) -> str:
    """Put back the spaces OCR drops inside titles ("ElectronicSub-Systems")."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", title)


def _field(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.I | re.S)
    return clean(m.group(1)) if m and clean(m.group(1)) else None


# A teaching-scheme row: "4 ECC-101 Introduction to Programming PCC 4 3 0 2/2 3 0 15-30 ...".
_STRUCTURE_ROW = re.compile(
    r"^(?:(Year [^:\n]+|Elective list): )?(?:\d+\.?\s+)?([A-Z]{2,4})\s*-\s*(\d{3}[A-Z]?)\s+(.+?)\s+"
    r"([A-Z]{2,5}(?:/[A-Z]{2,5})?)\s+(\d{1,2})\b(?:\s+(\d+)\s+(\d+)\s+(\d+(?:/\d+)?)\b)?",
    re.M,
)


def _structure_rows(text: str, url: str, title: str) -> list[dict]:
    """Courses listed only in a course-structure table, so they have no syllabus contents."""
    rows = []
    for m in _STRUCTURE_ROW.finditer(text):
        rows.append({
            "code": f"{m.group(2)}-{m.group(3)}",
            "title": _spaced(clean(m.group(4)))[:200],
            "department": None,
            "contact_hours": f"L:{m.group(7)} T:{m.group(8)} P:{m.group(9)}" if m.group(7) else None,
            "credits": m.group(6),
            "semester": m.group(1),
            "subject_area": m.group(5),
            "prerequisite": None,
            "objective": None,
            "contents": "",
            "source_url": url,
            "source_title": title,
        })
    return rows


def extract_courses(text: str, url: str, title: str) -> list[dict]:
    """One record per course form in a syllabus PDF, plus any course-structure table rows."""
    text = text.replace(" | ", " ")  # OCR marks column gaps; the field patterns don't expect them
    starts = list(_COURSE_START.finditer(text))
    courses = []
    for i, m in enumerate(starts):
        block = text[m.end():starts[i + 1].start() if i + 1 < len(starts) else len(text)]
        before = text[max(0, m.start() - 200):m.start()]
        dept = re.findall(r"NAME OF DEPT\.?/?\s*CENTRE\s*:\s*(.+)", before, re.I)
        details = re.search(r"Details of the Course\s*:?(.*)", block, re.I | re.S)
        body = details.group(1) if details else block
        # The next course's institute header isn't part of this one.
        body = re.split(r"INDIAN INSTITUTE OF TECHNOLOGY ROORKEE", body)[0].strip()
        courses.append({
            "code": f"{m.group(1).upper()}-{m.group(2).upper()}",
            "title": _spaced(clean(m.group(3)))[:200],
            "department": clean(dept[-1])[:120] if dept else None,
            "contact_hours": _field(r"Contact Hours\s*:\s*(L\s*:\s*\d+\s*T\s*:\s*\d+\s*P\s*:\s*\d+)", block),
            "credits": _field(r"Credits\s*:\s*(\d+)", block),
            "semester": _field(r"Semester\s*:?\s*([A-Za-z/ ,]+?)\s*(?:\d+\.|$|\n)", block),
            "subject_area": _field(r"Subject Area\s*:\s*([A-Za-z/ ]+)", block),
            "prerequisite": _field(r"Pre-?\s*requisite\s*:\s*(.+?)\s*(?:\d+\.\s*Objective|\n\d+\.)", block),
            "objective": _field(r"Objective\s*(?:of the Course|of Course)?\s*:\s*(.+?)\s*(?:\d+\.\s*Details|$)", block),
            "contents": body[:6000],
            "source_url": url,
            "source_title": title,
        })
    return courses + _structure_rows(text, url, title)
