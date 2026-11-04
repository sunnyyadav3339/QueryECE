"""Store course-structure PDFs that were downloaded elsewhere.

acad.iitr.ac.in is only reachable from the IITR network, so the weekly crawl on the
server can't fetch it (it then leaves the stored structures alone). On campus,
download the PDFs linked from COURSE_STRUCTURES_PAGE into a folder with an
index.json of [{"file": "...", "url": "...", "label": "..."}], copy the folder to
the server's /data, and run:

    python -m app.ingest.structures_upload /data/structure_upload
"""

import json
import sys
from pathlib import Path

from app.db.database import SessionLocal, init_db
from app.ingest.course_structure import CATEGORY, is_structure_pdf, lists_of, structure_title
from app.ingest.crawler import FetchedPage, normalize
from app.ingest.ocr import extract_pdf
from app.ingest.pipeline import _store_page


def main(folder: str) -> int:
    root = Path(folder)
    entries = json.loads((root / "index.json").read_text())
    init_db()
    stored = 0
    with SessionLocal() as db:
        for entry in entries:
            url = normalize(entry["url"])
            if not is_structure_pdf(url):
                print("skip (not a programme structure):", url)
                continue
            text, used_ocr = extract_pdf((root / entry["file"]).read_bytes())
            title = structure_title(entry.get("label", ""), url) + (" [scanned copy]" if used_ocr else "")
            page, _changed = _store_page(db, FetchedPage(url=url, title=title, text=text, is_pdf=True,
                                                         source_scanned=used_ocr), category=CATEGORY)
            minor = sum(len(rows) for _h, _n, rows in lists_of(text, "minor"))
            print(f"{page.title[:75]:77} {len(text):6} chars, {minor} minor courses")
            stored += 1
        db.commit()
    print(f"stored {stored} course structures")
    return 0 if stored else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "/data/structure_upload"))
