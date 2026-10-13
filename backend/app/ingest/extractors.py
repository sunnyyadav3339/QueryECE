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

from app.ingest.html_text import clean

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

