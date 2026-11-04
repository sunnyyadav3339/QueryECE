"""Course structures of every UG programme, from the Academic Affairs site.

Each programme's structure PDF ends with its course lists: Programme Electives (PEC),
Talent Enhancement Basket (TEB), Minor Specialization courses (which students of
other branches take for a minor), Departmental Honours courses (DHC, for the
department's own students) and Open Electives (OEC). These are stored as pages
but not indexed for search: twenty-one other departments' structures would crowd
ECE's own pages out of every answer. find_course_structure reads them instead.
"""

import re
from urllib.parse import unquote, urlsplit

ACAD_HOST = "acad.iitr.ac.in"
# Plain http: the https certificate of acad.iitr.ac.in expired in January 2026.
COURSE_STRUCTURES_PAGE = f"http://{ACAD_HOST}/Varsity/UGProgrammes_new1.html"
CATEGORY = "course_structure"


def is_structure_pdf(url: str) -> bool:
    """The current (2023-24 onwards) structure of one programme: UG_New/<dept>/....pdf.
    Files directly in UG_New/ are institute-wide syllabi, not structures."""
    parts = urlsplit(url)
    path = unquote(parts.path)
    return parts.netloc == ACAD_HOST and path.lower().endswith(".pdf") and bool(re.search(r"/UG_New/[^/]+/", path))


def structure_title(label: str, url: str) -> str:
    """'B. Tech. Civil Engineering(2023-24 onwards)  New' -> 'Course structure: B. Tech. Civil Engineering (2023-24 onwards)'."""
    label = re.sub(r"\s+", " ", label).strip()
    label = re.sub(r"\s*\bNew$", "", label)
    label = re.sub(r"(\S)\(", r"\1 (", label)
    return f"Course structure: {label or unquote(urlsplit(url).path.rsplit('/', 1)[-1])}"


# Programme names a student might use -> a fragment of that programme's PDF path.
# Order matters: the first match wins ("engineering physics" before "physics").
PROGRAMMES = [
    (r"electronics|\bece?\b", "/UG_New/EC/"),
    (r"computer|\bcse?\b", "/UG_New/CS/"),
    (r"electrical|\bee\b", "/UG_New/EE/"),
    (r"production|industrial|\bpie?\b", "/UG_New/ME/IN_"),
    (r"mechanical|\bme\b|\bmie\b", "/UG_New/ME/structure"),
    (r"civil|\bce\b", "/UG_New/CE/"),
    (r"chemical\s+eng|\bche?\b", "/UG_New/CH/"),
    (r"bio|\bbsbe\b|\bbt\b", "/UG_New/BT/"),
    (r"metallurg|materials|\bmme?\b|\bmt\b", "/UG_New/MT/"),
    (r"engineering\s+physics|\beph?\b|\bep\b", "/UG_New/EPH/"),
    (r"data\s+science|artificial|\bdsai\b|\bds\b|\bai\b|\bmfs\b", "/UG_New/MFS/"),
    (r"energy|\bhre\b", "/UG_New/HRE/"),
    (r"geophys", "/UG_New/IMT/ES/GPT"),
    (r"geolog", "/UG_New/IMT/ES/GT_"),
    (r"chemi|\bcy\b", "/UG_New/BS-MS/CY/"),
    (r"econ", "/UG_New/BS-MS/ECONOMICS/"),
    (r"math|\bmnc\b|\bma\b", "/UG_New/BS-MS/MA/"),
    (r"physics|\bph\b", "/UG_New/BS-MS/PH/"),
    (r"design|b\.?\s?des\b", "/UG_New/BDES/"),
    (r"arch", "/UG_New/AR/"),
]


def programme_path(name: str) -> str | None:
    for pattern, path in PROGRAMMES:
        if re.search(pattern, name, re.I):
            return path
    return None


KIND_LABELS = {
    "pec": "Programme Elective Courses (PEC)",
    "teb": "Talent Enhancement Basket courses (TEB)",
    "minor": "Minor Specialization courses (taken by students of other branches for a minor)",
    "honours": "Departmental Honours courses (DHC, for the department's own students)",
    "oec": "Open Elective courses (OEC, offered to other branches)",
}
# A heading line names a list; rows of the semester tables ("6 MSC/DHC-I Minor
# Specialization Course-I ...") start with a serial number and use the singular.
HEADINGS = [
    ("pec", re.compile(r"^(?:list\s+of\s+)?program(?:me)?\s+elective\s+(?:courses|list)|^PECs\s*\(", re.I)),
    ("teb", re.compile(r"^(?:list\s+of\s+|basket\s+of\s+)talent\s+enhancement|^talent\s+enhancement\s+courses\s*$", re.I)),
    ("minor", re.compile(r"^(?:list\s+of\s+)?minor\s+speciali[sz]ations?\s+c\w+rses|^list\s+of\s+minor|^minor\s+in\s+\w", re.I)),
    ("honours", re.compile(r"^(?:list\s+of\s+)?depart\w*\s*hono\w*\s+(?:speciali[sz]ation\s+)?courses|^list\s+of\s+depart\w*\s+hono", re.I)),
    ("oec", re.compile(r"^(?:list\s+of\s+)?open\s+elective\s+courses\s*:?\s*$|^list\s+of\s+(?:open\s+elective|oec)\s+courses?|^open\s+electives\s*:", re.I)),
    (None, re.compile(r"^list\s+of\s+engineering\s+science\s+courses", re.I)),  # ends the previous list
]

HYPHEN = "-\u2010\u2011\u2013"  # the PDFs mix ASCII, Unicode and en-dash hyphens
CODE = rf"[A-Z]{{2,4}}\s?[{HYPHEN}]\s?(?:\d{{3}}[A-Z]?|XXX)\b"  # XXX: a course not yet numbered
ROW_START = re.compile(rf"(?:(?<=\s)|^)(?:\d{{1,2}}\.?\s+)?(?={CODE})")
# The first table column after a course title.
COLUMN = re.compile(
    r"\s(?:(?:PEC|PCC|MSC|DHC|OEC|TEB|ESC|BSC|HSSEC|ESSC|MSC\s*/\s*DHC)\b|(?:Autumn|Spring|Both)\b|\d\s?-\s?\d\s?-\s?\d\b|\d(?:\s+[\d/-]+){2,})"
)
TABLE_HEADER = re.compile(
    r"S\.?\s?No\.?|Sub(?:ject)?\.?\s+Code|Course\s+(?:Code|Title)|Subject\s+Area|Credits?|Semester|Teaching\s+Scheme|"
    r"Contact\s+Hours?(?:/Week)?|Exam\.?\s+Duration|Relative\s+Weight\s*\(%\)|Theory|Practical|CWS|PRS|MTE|ETE|PRE|"
    r"\bL\b|\bT\b|\bP\b|L-T-P|Code|Title|\bCr\.?|Area|Th\.?|Pr\.?",
    re.I,
)


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def sections(text: str) -> list[tuple[str, str, str]]:
    """(kind, heading, body) for each course list in a structure PDF, in order."""
    found, current = [], None
    for line in text.splitlines():
        stripped = line.strip()
        kind = None
        if stripped and len(stripped) < 140 and not stripped[0].isdigit():
            for k, pattern in HEADINGS:
                if pattern.search(stripped):
                    kind = k or "end"
                    break
        if kind:
            current = None if kind == "end" else [kind, stripped, []]
            if current:
                found.append(current)
        elif current:
            current[2].append(line)
    return [(k, h, "\n".join(body)) for k, h, body in found]


def _row(piece: str) -> str | None:
    piece = _squash(piece)
    m = re.match(rf"(?:\d{{1,2}}\.?\s+)?({CODE})\s*(.*)$", piece)
    if not m:
        return None
    code = re.sub(rf"\s*[{HYPHEN}]\s*", "-", m.group(1))
    rest = m.group(2)
    col = COLUMN.search(" " + rest)
    title = (rest[:col.start()] if col else rest).strip(" -:,")
    tail = rest[col.start():] if col else ""
    sem = re.search(r"\b(Autumn|Spring|Both)\b", tail)
    credits = re.search(r"\b(?:PEC|PCC|MSC|DHC|OEC|TEB|ESC|MSC\s*/\s*DHC)\s+(\d)\b|\b(?:Autumn|Spring|Both)\s+(\d)\b|\d-\d-\d\s+(\d)\b", tail)
    facts = [x for x in (sem and sem.group(1), credits and f"{next(g for g in credits.groups() if g)} credits") if x]
    title = title[:110] or "(title not readable in the PDF)"
    return f"- {code} {title}" + (f" ({', '.join(facts)})" if facts else "")


def course_rows(body: str) -> tuple[str, list[str]]:
    """(note, rows): the section's lead text (minus table headers) and one line per course."""
    flat = _squash(body)
    starts = [m.start() for m in ROW_START.finditer(flat)]
    lead = flat[:starts[0]] if starts else flat
    lead = _squash(TABLE_HEADER.sub(" ", lead))
    # Leftover header letters ("C W S M E E E") aren't a note; a sentence or a basket name is.
    note = lead if len(re.findall(r"[A-Za-z]{3,}", lead)) >= 3 else ""
    rows = []
    for i, start in enumerate(starts):
        row = _row(flat[start:starts[i + 1] if i + 1 < len(starts) else len(flat)])
        if row:
            rows.append(row)
    return note[:300], list(dict.fromkeys(rows))


def lists_of(text: str, kind: str) -> list[tuple[str, str, list[str]]]:
    """(heading, note, rows) for every list of that kind. A programme without a separate
    honours list sometimes names one ("Program Elective Courses/ Departmental Honors Courses")."""
    out = []
    for k, heading, body in sections(text):
        if k == kind or (kind == "honours" and re.search(r"hono", heading, re.I)):
            note, rows = course_rows(body)
            # Some lists are a sentence in the heading itself: "Departmental Honours Courses: All PG ..."
            if rows or note or len(heading.split()) > 5:
                out.append((_squash(heading), note, rows))
    return out


def looks_misread(text: str) -> bool:
    """Two structures (B.Des, Energy Engineering) are scans with a poor OCR text layer:
    their titles come out as 'Vi ual Communication'. Clean PDFs score under 3, these about 5."""
    junk = re.findall(r"[!~€|{}·]|\b[Il1]{2,}\b|[a-z][A-Z]{2}[a-z]", text)
    return 1000 * len(junk) / max(1, len(text)) > 4
