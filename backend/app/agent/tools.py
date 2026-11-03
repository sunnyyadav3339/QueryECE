"""Tools the agent can call. Each returns compact text for the model and
registers the pages it used so answers can cite them as [n]."""

import hashlib
import re

from sqlalchemy import func, or_

from app.db.database import SessionLocal
from app.config import APP_URL
from app.db.models import Course, Faculty, Insight, InsightVote, Opportunity, Page, Project, Startup
from app.ingest.extractors import FacultyResolver, name_key
from app.rag import index
from app.rag.embeddings import cosine, embed_passages, embed_query
from app.rag.personal import match_texts

MAX_TOOL_CHARS = 6500  # ~1.8K tokens per tool result
FACULTY_DIRECTORY_URL = (
    "https://iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/"
    "People/Faculty/FACULTY%20MEMBERS.html"
)
PROJECTS_URL = (
    "https://iitr.ac.in/Departments/Electronics%20and%20Communication%20Engineering%20Department/"
    "Research/List%20of%20Sponsored%20Projects.html"
)


# The source table mixes acronyms and full names for the same agency.
AGENCY_ALIASES = {
    "SERB": ["Science and Engineering Research Board", "Science and Engineering Re-search Board", "ANRF"],
    "ANRF": ["Anusandhan National Research Foundation", "SERB"],
    "DST": ["Department of Science and Technology", "Department of Science & Technology"],
    "MEITY": ["Ministry of Electronics", "MeitY", "DeitY", "DIETY"],
    "DRDO": ["Defence Research", "Defense Research"],
    "ISRO": ["Indian Space Research", "Space Applications Centre"],
    "DBT": ["Department of Biotechnology"],
    "ICMR": ["Indian Council of Medical Research"],
    "SRC": ["Semiconductor Research Corporation"],
}


class SourceRegistry:
    """Assigns stable citation numbers to URLs across all tool calls in a turn."""

    def __init__(self):
        self.sources: list[dict] = []
        self._by_url: dict[str, int] = {}

    def ref(self, title: str, url: str) -> int:
        if url not in self._by_url:
            self.sources.append({"n": len(self.sources) + 1, "title": title, "url": url})
            self._by_url[url] = len(self.sources)
        return self._by_url[url]


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_department_info",
            "description": (
                "Semantic + keyword search over the scraped IIT Roorkee ECE department website "
                "(programmes, admissions, courses, labs, research groups, faculty profile pages incl. "
                "publications/patents/students, news, contacts, PDFs). Use for anything not covered by the other tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Self-contained search query (resolve pronouns from the chat)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_faculty",
            "description": (
                "Look up ECE faculty. Give `name` for one person's contact details, designation, interests, "
                "resume/CV status, projects and startups; or `research_topic` to rank faculty whose research "
                "matches a topic; or `with_resume` to list every faculty member with a resume/CV on file; "
                "or no arguments for the whole directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "research_topic": {"type": "string"},
                    "with_resume": {"type": "boolean", "description": "List exactly the faculty who have a resume/CV."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_sponsored_projects",
            "description": "Filter the department's sponsored research projects (PI, title, funding agency, co-PI, year).",
            "parameters": {
                "type": "object",
                "properties": {
                    "faculty_name": {"type": "string"},
                    "keyword": {"type": "string", "description": "Word(s) to match in the project title"},
                    "agency": {"type": "string", "description": "e.g. DST, SERB, ISRO, MeitY"},
                    "since_year": {"type": "integer"},
                    "limit": {"type": "integer", "default": 10},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_opportunities",
            "description": "Current job adverts from IITR career pages (project jobs: RA/JRF/SRF/project associate; post-doc fellowships).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ece_only": {"type": "boolean", "default": True},
                    "keyword": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_time_table",
            "description": (
                "The official weekly class time table of one programme and year: what class is on which weekday, "
                "slot and room. Not for dates such as when a semester or classes start, exams or holidays: those "
                "are in the academic calendar (search_department_info). Sem 1-2 = year I, 3-4 = II, 5-6 = III, 7-8 = IV."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "programme": {"type": "string", "description": "B.Tech ECE, CNSP, RF, VLSI, THz or Semiconductor."},
                    "year": {"type": "string", "description": "I, II, III or IV. M.Tech time tables are year I."},
                    "day": {"type": "string", "description": "Optional weekday, e.g. Tuesday."},
                    "teacher": {"type": "string", "description": "A teacher's name, to list their classes across all programmes and years. Then programme and year aren't needed."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_course",
            "description": (
                "Exact course details from the official syllabus PDFs: credits, L-T-P hours, semester, subject area, "
                "pre-requisites, objective and syllabus contents. Look up by course code (ECN-342) or by title/topic. "
                "Also gives the full list for a term of a programme's course structure, e.g. 'B.Tech Year I Autumn'."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Course code or words from the title or contents."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_senior_insights",
            "description": (
                "Tips written by IITR students/seniors that are NOT on any website: experiences with professors "
                "(reply habits, what they look for), BTP/projects, courses and electives, interviews, internships. "
                "Use alongside official tools for advice or 'what is it like' questions. Unofficial and anecdotal."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What to look for, incl. professor/course names."}},
                "required": ["query"],
            },
        },
    },
]


def _clip(text: str, limit: int = MAX_TOOL_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + "\n…(truncated)"


# ---------------------------------------------------------------------------


# The site spells these out on some pages and abbreviates on others, so a search
# for either form has to find both.
ACRONYMS = {
    "DAPC": "Department Academic Program Committee",
    "DRC": "Department Research Committee",
    "HOD": "Head of the Department",
    "FIC": "Faculty In-Charge",
    "BTP": "B.Tech Project",
    "JMDP": "Joint Masters Degree Programme",
}


def _expand_acronyms(query: str) -> str:
    extra = [full for short, full in ACRONYMS.items() if re.search(rf"\b{short}\b", query, re.I)]
    # Pages often use only the short form: "Prof. X (FIC, Time Table)".
    extra += [short for short, full in ACRONYMS.items() if full.lower() in query.lower()]
    if "FIC" not in extra and re.search(r"in-?\s?charge", query, re.I):
        extra.append("FIC")
    return f"{query} ({'; '.join(extra)})" if extra else query


def _with_course_titles(text: str) -> str:
    """Name the course codes in a result, so the model never has to guess what one is."""
    codes = {f"{a}-{b}" for a, b in re.findall(r"\b([A-Z]{2,4})\s?-\s?(\d{3}[A-Z]?)\b", text)}
    if not codes:
        return text
    with SessionLocal() as db:
        rows = db.query(Course.code, Course.title).filter(Course.code.in_(codes)).order_by(Course.code).limit(30).all()
    named = "; ".join(f"{code} = {title}" for code, title in rows)
    return f"{text}\n\nOfficial titles of the course codes above: {named}" if named else text


YEAR_WORDS = {"first": "I", "1st": "I", "1": "I", "second": "II", "2nd": "II", "2": "II",
              "third": "III", "3rd": "III", "3": "III", "fourth": "IV", "4th": "IV", "4": "IV"}
YEAR_IN_QUERY = re.compile(r"\b(first|1st|second|2nd|third|3rd|fourth|4th)[\s-]*year\b|\byear\s*:?\s*(IV|I{1,3}|[1-4])\b", re.I)


def _courses_in_term(db, query: str) -> list[Course]:
    """All courses of one year (and semester) in the course structures, e.g. "B.Tech Year I Autumn"."""
    year = YEAR_IN_QUERY.search(query)
    if not year:
        return []
    word = (year.group(1) or year.group(2)).lower()
    numeral = YEAR_WORDS.get(word, word.upper())
    term = re.search(r"\b(autumn|spring)\b", query, re.I)
    q = db.query(Course).filter(Course.semester.ilike(f"Year {numeral} {term.group(1) if term else ''}%"))
    if not re.search(r"m\.?\s?tech|vlsi|cnsp|\brf\b|microwave|thz|terahertz|semiconductor", query, re.I):
        q = q.filter(Course.source_url.ilike("%btech%"))
    return q.order_by(Course.semester, Course.code).limit(40).all()


TIMETABLE_ROW = re.compile(r"^(.+? Year \S+) \| (.+)$", re.M)
TIMETABLE_ALIASES = (
    ("M.Tech CNSP", r"cnsp|signal|network"), ("M.Tech RF", r"\brf\b|r\.f|microwave"),
    ("M.Tech VLSI", r"vlsi|microelectronic"), ("M.Tech THz", r"thz|terahertz"),
    ("M.Tech Semiconductor", r"semiconductor"), ("B.Tech ECE", r"b\.?\s?tech|\bece\b|electronics"),
)


TIMETABLE_CELL = re.compile(r"(?=\b[LTP]\s*[A-Z]{2,4}-\d{3})")


def _squashed(text: str) -> str:
    return re.sub(r"\W", "", text).lower()  # OCR drops spaces in names: "BrijeshKumar"


def _classes_of_teacher(reg: SourceRegistry, pages: list[Page], teacher: str, day: str) -> str:
    name = _squashed(re.sub(r"\b(prof|proff|professor|dr)\b\.?", "", teacher, flags=re.I))
    blocks = []
    for page in pages:
        found: dict[str, list[str]] = {}
        for label, row in TIMETABLE_ROW.findall(page.text or ""):
            if ": " not in row or (day and not row.lower().startswith(day.lower())):
                continue
            # One slot can hold several classes: "P ECC-101 26EC3 Brijesh Kumar P PHI-101 26EC1".
            slot, cells = row.split(": ", 1)
            own = [cell.strip() for cell in TIMETABLE_CELL.split(cells) if name in _squashed(cell)]
            if own:
                found.setdefault(label, []).append(f"{slot}: {' / '.join(own)}")
        if found:
            n = reg.ref(f"{page.title.split(' (')[0]} (time tables)", page.url)
            blocks += [f"[{n}] {label}:\n" + "\n".join(rows) for label, rows in found.items()]
    if not blocks:
        return f"{teacher} doesn't appear in any published time table."
    return _with_course_titles(_clip("Current term, from scanned copies:\n" + "\n\n".join(blocks)))


def find_time_table(reg: SourceRegistry, programme: str = "", year: str = "", day: str = "", teacher: str = "", **_ignored) -> str:
    if teacher:
        with SessionLocal() as db:
            pages = db.query(Page).filter(Page.active.is_(True), Page.title.ilike("%Timetable%")).all()
            return _classes_of_teacher(reg, pages, teacher, day)
    programme_name = next((name for name, pattern in TIMETABLE_ALIASES if re.search(pattern, programme, re.I)), "")
    numeral = YEAR_WORDS.get(year.strip().lower(), year.strip().upper())
    wanted = f"{programme_name} Year {numeral}"
    with SessionLocal() as db:
        pages = db.query(Page).filter(Page.active.is_(True), Page.title.ilike("%Timetable%")).all()
        published, rows, source = set(), [], None
        for page in pages:
            for label, row in TIMETABLE_ROW.findall(page.text or ""):
                published.add(label)
                if label == wanted and (not day or row.lower().startswith((day.lower(), "all days"))):
                    rows.append(row)
                    source = page
    if not rows:
        return (f"No time-table rows for {wanted} {day}. The website publishes time tables only for: "
                f"{', '.join(sorted(published))}. Tell the student this; do not use another programme's or year's rows.")
    term = re.search(r"(Autumn|Spring)\s*\d{4}-\d{2}", source.text or "")
    n = reg.ref(f"{wanted} time table", source.url)
    header = f"[{n}] {wanted} time table, {term.group(0) if term else 'term not stated'} (scanned copy)"
    return _with_course_titles(_clip(f"{header}\n" + "\n".join(rows)))


def find_course(reg: SourceRegistry, query: str, **_ignored) -> str:
    code = re.search(r"\b([A-Za-z]{2,4})\s*-?\s*(\d{3}[A-Za-z]?)\b", query)
    with SessionLocal() as db:
        rows = []
        if code:
            exact = db.get(Course, f"{code.group(1).upper()}-{code.group(2).upper()}")
            rows = [exact] if exact else []
        if not rows:
            rows = _courses_in_term(db, query)
        if not rows:
            words = [w for w in re.findall(r"[A-Za-z0-9&+-]{3,}", query)]
            q = db.query(Course)
            for word in words[:6]:
                q = q.filter(or_(Course.title.ilike(f"%{word}%"), Course.contents.ilike(f"%{word}%")))
            rows = q.order_by(Course.code).limit(8).all()
        if not rows:
            return "No matching course in the syllabus PDFs. Try search_department_info, or the course-structure documents."
        full = len(rows) <= 2
        blocks = []
        for c in rows:
            n = reg.ref(c.source_title or "Syllabus", c.source_url)
            facts = " | ".join(f"{k}: {v}" for k, v in (
                ("Hours", c.contact_hours), ("Credits", c.credits), ("Semester", c.semester), ("Area", c.subject_area),
                ("Pre-requisite", c.prerequisite), ("Department", c.department)) if v)
            block = f"[{n}] {c.code} {c.title}\n{facts}"
            if full and c.contents:
                block += f"\nObjective: {c.objective or 'not stated'}\nContents:\n{c.contents}"
            elif full:
                block += "\nListed in the course structure only; its syllabus contents were not found."
            blocks.append(block)
        return _with_course_titles(_clip("\n\n".join(blocks)))


STARTUP_QUERY = re.compile(r"\b(start-?\s?ups?|spin-?\s?offs?|incubat\w*)\b", re.I)


def _startup_blocks(reg: SourceRegistry) -> list[str]:
    """The department's faculty-led startups, which a general search often ranks below passing mentions."""
    with SessionLocal() as db:
        page = db.query(Page).filter(Page.active.is_(True), Page.url.like("%Faculty%Led%Startups%")).first()
        startups = db.query(Startup).order_by(Startup.name).all()
        if not page or not startups:
            return []
        n = reg.ref("Faculty Led Startups", page.url)
        return [f"[{n}] {s.name} | Founder: {s.founder_raw or 'not stated'} | Website: {s.website or 'not stated'}\n"
                f"{s.description or ''}" for s in startups]


def search_department_info(reg: SourceRegistry, query: str, **_ignored) -> str:
    # A term's course list is split across chunks of the PDF; the course table has all of it.
    if re.search(r"\b(courses?|subjects?|curriculum)\b", query, re.I) and YEAR_IN_QUERY.search(query):
        return find_course(reg, query)
    # No section filter: the model's category guesses (e.g. "research" for a PhD
    # interview PDF) excluded the right pages more often than they helped.
    blocks = _startup_blocks(reg) if STARTUP_QUERY.search(query) else []
    hits = index.search(_expand_acronyms(query), k=3 if blocks else 5)
    if not hits and not blocks:
        return "This search found nothing on the department website."
    for hit in hits:
        n = reg.ref(hit.title, hit.url)
        blocks.append(f"[{n}] {hit.text[:1300]}")  # whole chunk (~1200 chars + header)
    # Kept outside _clip so truncation can't drop it.
    return _with_course_titles(_clip("\n\n".join(blocks))) + (
        "\n\n(These are the few best-matching passages, not a complete list: never present them as all there is.)")


_faculty_vec_cache: dict[str, list[float]] = {}


def _faculty_vectors(faculty: list[Faculty]) -> list[list[float]]:
    texts = [f"{f.name}. {f.designation or ''}. Research: {f.interests or ''}" for f in faculty]
    keys = [hashlib.md5(t.encode()).hexdigest() for t in texts]
    missing = [(k, t) for k, t in zip(keys, texts) if k not in _faculty_vec_cache]
    if missing:
        for (k, _), vec in zip(missing, embed_passages([t for _, t in missing])):
            _faculty_vec_cache[k] = vec
    return [_faculty_vec_cache[k] for k in keys]


def _faculty_card(f: Faculty, reg: SourceRegistry) -> str:
    n = reg.ref(f"{f.name} — faculty profile", f.profile_url or FACULTY_DIRECTORY_URL)
    parts = [f"[{n}] {f.name} — {f.designation or 'Faculty'}"]
    if f.email:
        parts.append(f"Email: {f.email}")
    if f.phone:
        parts.append(f"Phone: {f.phone}")
    if f.website:
        parts.append(f"Website: {f.website}")
    if f.interests:
        parts.append(f"Research interests: {f.interests}")
    if f.resume_url:
        parts.append(f"Resume / CV: available [{reg.ref(f'Resume / CV: {f.name}', f.resume_url)}]")
    elif f.resume_url == "":
        parts.append("Resume / CV: none uploaded on the department profile")
    return "\n".join(parts)


def find_faculty(reg: SourceRegistry, name: str | None = None, research_topic: str | None = None,
                 with_resume: bool = False, **_ignored) -> str:
    with SessionLocal() as db:
        faculty = db.query(Faculty).all()
        if not faculty:
            return "Faculty directory is empty (the website has not been indexed yet)."

        if with_resume and not name and not research_topic:
            have = sorted((f for f in faculty if f.resume_url), key=lambda f: f.name)
            if not have and all(f.resume_url is None for f in faculty):
                return "Which faculty have a resume isn't known yet (profiles not indexed since this was added)."
            lines = [f"Complete list: {len(have)} of {len(faculty)} ECE faculty have a resume / CV on their "
                     "department profile (the rest have none uploaded):"]
            lines += [f"- {f.name} — {f.designation or ''} "
                      f"[{reg.ref(f'Resume / CV: {f.name}', f.resume_url)}]" for f in have]
            return _clip("\n".join(lines))

        if name:
            resolver = FacultyResolver([(f.id, f.name) for f in faculty])
            fid = resolver.resolve(name, min_score=70)
            matches = [f for f in faculty if f.id == fid] if fid else [
                f for f in faculty if name_key(name) and name_key(name) in name_key(f.name)
            ]
            if not matches:
                return f"No ECE faculty member matching '{name}'. Directory has {len(faculty)} members."
            out = []
            for f in matches[:3]:
                block = [_faculty_card(f, reg)]
                projects = (db.query(Project).filter_by(faculty_id=f.id)
                            .order_by(Project.year.desc()).limit(8).all())
                if projects:
                    pn = reg.ref("List of Sponsored Projects", PROJECTS_URL)
                    block.append(f"Sponsored projects as PI [{pn}]:")
                    block += [f"- {p.title} ({p.agency or 'agency n/a'}, {p.year or 'year n/a'})" for p in projects]
                for s in db.query(Startup).filter_by(faculty_id=f.id).all():
                    block.append(f"Startup: {s.name} — {s.website or ''}")
                block.append("(For publications, students, education or patents, use search_department_info "
                             "with the faculty name.)")
                out.append("\n".join(block))
            return _clip("\n\n".join(out))

        if research_topic:
            qv = embed_query(research_topic)
            vectors = _faculty_vectors(faculty)
            terms = [t for t in re.findall(r"[a-z0-9]+", research_topic.lower()) if len(t) > 2]
            scored = []
            for f, vec in zip(faculty, vectors):
                score = cosine(qv, vec)
                hay = (f.interests or "").lower()
                score += 0.03 * sum(t in hay for t in terms)  # small exact-term bonus
                scored.append((score, f))
            scored.sort(key=lambda x: x[0], reverse=True)
            out = [f"Faculty ranked by fit to '{research_topic}' (best first):"]
            for _score, f in scored[:6]:
                out.append(_faculty_card(f, reg))
            return _clip("\n\n".join(out))

        n = reg.ref("ECE Faculty Members", FACULTY_DIRECTORY_URL)
        lines = [f"[{n}] ECE faculty ({len(faculty)}):"]
        lines += [f"- {f.name} — {f.designation or ''} — {f.email or ''}" + (" — has resume/CV" if f.resume_url else "")
                  for f in sorted(faculty, key=lambda f: f.name)]
        return _clip("\n".join(lines))


def list_sponsored_projects(reg: SourceRegistry, faculty_name=None, keyword=None, agency=None,
                            since_year=None, limit=10) -> str:
    limit = max(1, min(int(limit or 10), 25))
    with SessionLocal() as db:
        q = db.query(Project)
        if faculty_name:
            faculty = db.query(Faculty).all()
            fid = FacultyResolver([(f.id, f.name) for f in faculty]).resolve(faculty_name, min_score=70)
            surname = name_key(faculty_name).split()[-1] if name_key(faculty_name) else faculty_name
            conds = [Project.faculty_raw.ilike(f"%{surname}%"), Project.co_pi.ilike(f"%{surname}%")]
            if fid:
                conds.append(Project.faculty_id == fid)
            q = q.filter(or_(*conds))
        if keyword:
            for word in keyword.split():
                q = q.filter(Project.title.ilike(f"%{word}%"))
        if agency:
            names = AGENCY_ALIASES.get(agency.strip().upper(), []) + [agency.strip()]
            q = q.filter(or_(*[Project.agency.ilike(f"%{n}%") for n in names]))
        rows = q.order_by(Project.year.desc()).all()
        if since_year:
            rows = [p for p in rows if (p.year or "")[:4].isdigit() and int(p.year[:4]) >= int(since_year)]
        if not rows:
            return "No sponsored projects match those filters."
        n = reg.ref("List of Sponsored Projects", PROJECTS_URL)
        lines = [f"[{n}] {len(rows)} matching projects (showing {min(limit, len(rows))}):"]
        for p in rows[:limit]:
            co = f"; co-PI: {p.co_pi}" if p.co_pi else ""
            lines.append(f"- {p.title} — PI: {p.faculty_raw}{co}; agency: {p.agency or 'n/a'}; year: {p.year or 'n/a'}")
        return _clip("\n".join(lines))


def list_opportunities(reg: SourceRegistry, ece_only: bool = True, keyword: str | None = None) -> str:
    with SessionLocal() as db:
        q = db.query(Opportunity).filter(Opportunity.active.is_(True))
        if keyword:
            q = q.filter(or_(Opportunity.title.ilike(f"%{keyword}%"), Opportunity.details.ilike(f"%{keyword}%")))
        rows = q.order_by(Opportunity.id.desc()).all()
        ece = [o for o in rows if o.is_ece]
        chosen = ece if ece_only else rows
        lines = []
        if ece_only and not ece:
            lines.append(f"No open ECE-department adverts right now. {len(rows)} openings exist in other departments "
                         "(call again with ece_only=false to see them).")
        for o in chosen[:12]:
            n = reg.ref(o.title[:80], o.url)
            line = f"[{n}] {o.kind}: {o.title}"
            if o.details:
                line += f"\n   Advert excerpt: {o.details[:500]}"
            lines.append(line)
        return _clip("\n".join(lines) or "No openings found.")


def search_senior_insights(reg: SourceRegistry, query: str, **_ignored) -> str:
    from app.routers.insights import CATEGORIES  # local import: routers import tools indirectly

    with SessionLocal() as db:
        rows = db.query(Insight).filter(Insight.hidden.is_(False)).order_by(Insight.created_at.desc()).limit(400).all()
        if not rows:
            return "No senior insights have been shared yet."
        names = {f.id: f.name for f in db.query(Faculty.id, Faculty.name)}
        helpful = _count_helpful(db)
        texts = [(str(r.id), " ".join(x for x in (CATEGORIES.get(r.category, ""), names.get(r.faculty_id) or "",
                                                  r.subject or "", r.body) if x)) for r in rows]
        scores = match_texts(texts, [query])
        q = query.lower()
        ranked = []
        for r in rows:
            score = scores[str(r.id)][0]
            name = names.get(r.faculty_id)
            if name and name.lower().split()[-1] in q:  # asked about this professor by name
                score += 0.15
            ranked.append((score, r))
        ranked = [x for x in sorted(ranked, key=lambda x: -x[0]) if x[0] >= 0.58][:5]
        if not ranked:
            return "No senior insights match this question."
        blocks = []
        for _score, r in ranked:
            label = CATEGORIES.get(r.category, r.category)
            about = f" · about Prof. {names[r.faculty_id]}" if r.faculty_id in names else ""
            subj = f" · {r.subject}" if r.subject else ""
            n = reg.ref(f"Senior insight · {label}{about}", f"{APP_URL}/insights?id={r.id}")
            votes = helpful.get(r.id, 0)
            blocks.append(f"[{n}] (Senior insight, unofficial{about}{subj}; {votes} found it helpful) {r.body}")
        return _clip("\n\n".join(blocks))


def _count_helpful(db) -> dict[int, int]:
    return dict(db.query(InsightVote.insight_id, func.count()).filter(InsightVote.kind == "helpful")
                .group_by(InsightVote.insight_id).all())


REGISTRY = {
    "search_department_info": search_department_info,
    "find_faculty": find_faculty,
    "list_sponsored_projects": list_sponsored_projects,
    "list_opportunities": list_opportunities,
    "search_senior_insights": search_senior_insights,
    "find_course": find_course,
    "find_time_table": find_time_table,
}

STATUS_TEXT = {
    "search_department_info": "Searching the department website",
    "find_faculty": "Looking up faculty",
    "list_sponsored_projects": "Checking sponsored projects",
    "list_opportunities": "Checking open positions",
    "search_senior_insights": "Reading seniors' insights",
    "find_course": "Checking the syllabus",
    "find_time_table": "Reading the time table",
}
