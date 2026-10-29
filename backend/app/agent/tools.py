"""Tools the agent can call. Each returns compact text for the model and
registers the pages it used so answers can cite them as [n]."""

import hashlib
import re

from sqlalchemy import func, or_

from app.db.database import SessionLocal
from app.config import APP_URL
from app.db.models import Faculty, Insight, InsightVote, Opportunity, Project, Startup
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
                "projects and startups; or `research_topic` to rank faculty whose research matches a topic."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "research_topic": {"type": "string"},
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


def search_department_info(reg: SourceRegistry, query: str, **_ignored) -> str:
    # No section filter: the model's category guesses (e.g. "research" for a PhD
    # interview PDF) excluded the right pages more often than they helped.
    hits = index.search(query, k=5)
    if not hits:
        return "No matching content found on the department website."
    blocks = []
    for hit in hits:
        n = reg.ref(hit.title, hit.url)
        blocks.append(f"[{n}] {hit.text[:1300]}")  # whole chunk (~1200 chars + header)
    return _clip("\n\n".join(blocks))


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
    return "\n".join(parts)


def find_faculty(reg: SourceRegistry, name: str | None = None, research_topic: str | None = None) -> str:
    with SessionLocal() as db:
        faculty = db.query(Faculty).all()
        if not faculty:
            return "Faculty directory is empty (the website has not been indexed yet)."

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
        lines += [f"- {f.name} — {f.designation or ''} — {f.email or ''}" for f in sorted(faculty, key=lambda f: f.name)]
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
}

STATUS_TEXT = {
    "search_department_info": "Searching the department website",
    "find_faculty": "Looking up faculty",
    "list_sponsored_projects": "Checking sponsored projects",
    "list_opportunities": "Checking open positions",
    "search_senior_insights": "Reading seniors' insights",
}
