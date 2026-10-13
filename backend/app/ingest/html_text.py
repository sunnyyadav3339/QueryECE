"""Turn an IITR CMS page into heading-structured plain text.

The IITR site is server-rendered by one CMS, so every page shares the same
chrome (.header, .menuContainer, .footer-container) around the content.
Output format, consumed by the chunker:

    ## Heading
    paragraph line
    Col A: v1 | Col B: v2        <- one line per table row
"""

import re

from bs4 import BeautifulSoup, NavigableString, Tag

CHROME_SELECTORS = [
    ".header", ".menuContainer", ".footer-container", ".title-box",
    ".vertical-list",  # faculty profile left-hand tab list
]
SKIP_TAGS = {"script", "style", "noscript", "svg", "img", "button", "select",
             "option", "input", "iframe", "head"}
BLOCK_TAGS = {"p", "div", "li", "ul", "ol", "section", "article", "tr", "br",
              "h1", "h2", "h3", "h4", "h5", "h6", "dd", "dt", "blockquote"}
HEADING_CLASSES = ("section-heading", "section-heading-blue", "sub-heading")
LINK_WORDS = re.compile(r"^(view|download|click here|here|link|pdf|read more|website)$", re.I)


def clean(text: str) -> str:
    return " ".join((text or "").replace("\xa0", " ").split())


def _is_heading(tag: Tag) -> bool:
    if tag.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return True
    classes = tag.get("class") or []
    return any(c in HEADING_CLASSES for c in classes)


def table_to_lines(table: Tag) -> list[str]:
    rows = []
    for tr in table.find_all("tr"):
        cells = [clean(c.get_text(" ")) for c in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(cells)
    if not rows:
        return []
    header = rows[0]
    has_header = bool(table.find("th")) or len(rows) > 1
    lines = []
    for cells in rows[1:] if has_header else rows:
        if has_header and len(cells) == len(header):
            parts = [f"{h}: {v}" for h, v in zip(header, cells) if v and h]
        else:
            parts = [v for v in cells if v]
        if parts:
            lines.append(" | ".join(parts))
    return lines


def _walk(node: Tag, out: list[tuple[str, str]], base_url: str):
    for child in node.children:
        if isinstance(child, NavigableString):
            if child.__class__.__name__ in ("Comment", "Doctype"):
                continue
            t = clean(str(child))
            if t:
                out.append(("text", t))
            continue
        if not isinstance(child, Tag) or child.name in SKIP_TAGS:
            continue
        if child.name == "table":
            out.append(("break", ""))
            out.extend(("line", line) for line in table_to_lines(child))
            continue
        if _is_heading(child):
            t = clean(child.get_text(" "))
            if t:
                out.append(("heading", t))
            continue
        if child.name == "a" and child.get("href"):
            text = clean(child.get_text(" "))
            href = child["href"].strip()
            # Keep URLs for generic link text ("view", "download"...) and PDFs
            # so the assistant can point students at the actual document.
            if href.startswith("http") and (not text or LINK_WORDS.match(text) or href.lower().endswith(".pdf")):
                out.append(("text", f"{text} ({href})" if text else href))
                continue
        _walk(child, out, base_url)
        if child.name in BLOCK_TAGS or "ui" in (child.get("class") or []):
            out.append(("break", ""))


def page_title(soup: BeautifulSoup) -> str:
    title = clean(soup.title.get_text()) if soup.title else ""
    return title or "IIT Roorkee ECE"


def html_to_text(html: str, url: str = "") -> tuple[str, str, BeautifulSoup]:
    """Return (title, structured_text, soup). The soup is reused by extractors."""
    soup = BeautifulSoup(html, "lxml")
    title = page_title(soup)
    content = BeautifulSoup(html, "lxml")
    for selector in CHROME_SELECTORS:
        for el in content.select(selector):
            el.decompose()
    body = content.body or content

    tokens: list[tuple[str, str]] = []
    _walk(body, tokens, url)

    lines: list[str] = []
    buffer: list[str] = []

    def flush():
        if buffer:
            line = clean(" ".join(buffer))
            if line:
                lines.append(line)
            buffer.clear()

    for kind, value in tokens:
        if kind == "text":
            buffer.append(value)
        elif kind == "break":
            flush()
        elif kind == "line":
            flush()
            lines.append(value)
        elif kind == "heading":
            flush()
            lines.append(f"## {value}")
    flush()

    # Collapse duplicate consecutive lines (the CMS repeats page titles).
    deduped = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)
    return title, "\n".join(deduped), soup


def pdf_to_text(data: bytes, max_pages: int = 15) -> str:
    from io import BytesIO

    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    parts = []
    for page in reader.pages[:max_pages]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:  # malformed pages are common in scanned adverts
            continue
    text = "\n".join(parts)
    lines = [clean(line) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
