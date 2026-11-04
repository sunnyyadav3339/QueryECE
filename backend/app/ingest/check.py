"""Pre-demo data check: confirms the index and tools give what a demo relies on.

Deterministic (no LLM calls, nothing written), so it is safe to run on the live
server after each crawl:

    python -m app.ingest.check

Exits 1 if any check fails. It checks data and tool results, not the model's
wording, so still try a few real questions in the app before a demo.
"""

import re
import sys

from app.agent import tools
from app.db.database import SessionLocal, init_db
from app.db.models import Chunk, Course, Faculty, Page
from app.ingest.photos import photo_path
from app.ingest.privacy import redact_applicant_lists
from app.rag import index

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = ""):
    results.append((ok, f"{label}{': ' + detail if detail else ''}"))


def main() -> int:
    init_db()
    with SessionLocal() as db:
        pages = db.query(Page).filter(Page.active.is_(True)).all()
        faculty = db.query(Faculty).all()
        check(len(pages) >= 200, "pages indexed", f"{len(pages)} active")
        chunks, vectors = db.query(Chunk).count(), index.count()
        check(chunks == vectors, "keyword and vector index agree", f"{chunks} chunks, {vectors} vectors")

        # Privacy: nothing left that the applicant-list filter would still cut.
        named = [p.title for p in pages if redact_applicant_lists(p.text or "") != (p.text or "")]
        check(not named, "no named applicant lists", ", ".join(named[:5]))

        # Resumes: every profile states it, and each listed resume is indexed.
        bare = [p.title for p in pages if p.category == "faculty_profile"
                and re.search(r"^Download Resume\b", p.text or "", re.M)]
        check(not bare, "profiles say whether a resume exists", f"{len(bare)} still show only the button label")
        unknown = [f.name for f in faculty if f.resume_url is None]
        check(not unknown, "resume status known for every faculty member", ", ".join(unknown[:5]))
        have = [f for f in faculty if f.resume_url]
        page_urls = {p.url for p in pages}
        missing = [f.name for f in have if f.resume_url not in page_urls]
        check(not missing, f"all {len(have)} resumes are indexed",
              "not fetched (needs the IITR network): " + ", ".join(missing) if missing else "")
        listed = tools.find_faculty(tools.SourceRegistry(), with_resume=True)
        wrong = [f.name for f in faculty if (f"- {f.name} —" in listed) != bool(f.resume_url)]
        check(not wrong, "find_faculty(with_resume) lists exactly the faculty with a resume", ", ".join(wrong))

        no_photo = [f.name for f in faculty if f.image_url and not photo_path(f.id)]
        check(not no_photo, "faculty photos saved", f"missing for {len(no_photo)} (needs the IITR network)")

        courses = db.query(Course).count()
        check(courses > 0, "course table filled", f"{courses} courses")

    timetable = tools.find_time_table(tools.SourceRegistry(), programme="B.Tech", year="2", day="Monday")
    check(not timetable.startswith("No time-table rows"), "time table lookup answers", timetable[:80].replace("\n", " "))
    course = tools.find_course(tools.SourceRegistry(), "ECN")
    check(not course.startswith("No matching course"), "course lookup answers")
    search = tools.search_department_info(tools.SourceRegistry(), "PhD admission")
    check("not a complete list" in search, "search results are marked as partial")

    with SessionLocal() as db:
        structures = db.query(Page).filter(Page.category == "course_structure", Page.active.is_(True)).count()
    check(structures >= 15, "UG course structures stored", f"{structures} programmes")
    reg = tools.SourceRegistry()
    minors = tools.find_course_structure(reg, programme="ECE", list_type="minor")
    rows = re.findall(r"^- [A-Z]{2,4}-\d{3}", minors, re.M)
    check(len(rows) >= 5, "ECE minor courses listed", f"{len(rows)} courses")
    every = tools.find_course_structure(reg, list_type="minor")
    check(every.count("\n[") >= 10, "minor courses of other departments listed", f"{every.count(chr(10) + '[')} departments")

    for ok, line in results:
        print(("PASS " if ok else "FAIL ") + line)
    failed = sum(not ok for ok, _ in results)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
