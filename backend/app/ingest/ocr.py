"""PDF text extraction with OCR for scanned pages.

Text PDFs are read directly. Pages with no text layer (the department's time
tables and several course structures are scanned) go through RapidOCR, which
runs on CPU with bundled ONNX models. OCR is slow, so results are cached by file
hash under data/ocr_cache/ and re-crawls of an unchanged PDF cost nothing.

Time tables get special handling: plain row-by-row OCR jumbles multi-line
cells, so text boxes are placed on the grid defined by the weekday header and
the time column, giving "Monday 10.00-10.55: ..." lines.
"""

import hashlib
import logging
import re
from io import BytesIO

from app.config import DATA_DIR
from app.ingest.html_text import clean

log = logging.getLogger(__name__)

CACHE_DIR = DATA_DIR / "ocr_cache"
MIN_PAGE_CHARS = 25  # below this a page is treated as scanned
MAX_TEXT_PAGES = 300
MAX_OCR_PAGES = 25
RENDER_SCALE = 3.0  # ~216 dpi: small table text needs it
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
TIME_RE = re.compile(r"^\d{1,2}[.:]\d{2}")

_engine = None


def _ocr_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _engine = RapidOCR()
    return _engine


def _boxes(pil_image) -> list[dict]:
    """OCR one page into boxes with left/right/centre coordinates."""
    import numpy as np

    result, _ = _ocr_engine()(np.array(pil_image.convert("RGB")))
    boxes = []
    for points, text, _conf in result or []:
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        text = clean(text)
        if text:
            boxes.append({"text": text, "left": min(xs), "right": max(xs), "top": min(ys), "bottom": max(ys),
                          "x": sum(xs) / 4, "y": sum(ys) / 4, "h": max(ys) - min(ys)})
    return boxes


def _reading_order(boxes: list[dict]) -> list[str]:
    """Group boxes into lines by vertical position, left to right within a line."""
    lines: list[list[dict]] = []
    for box in sorted(boxes, key=lambda b: b["y"]):
        if lines and abs(box["y"] - lines[-1][-1]["y"]) < max(box["h"], lines[-1][-1]["h"]) * 0.6:
            lines[-1].append(box)
        else:
            lines.append([box])
    return [" | ".join(b["text"] for b in sorted(line, key=lambda b: b["left"])) for line in lines]


def _fill_missing_days(days: dict[str, dict]) -> None:
    """Place a weekday whose header OCR misread, or its classes would land in the column beside it."""
    order = [d for d in WEEKDAYS[:5]]
    for i, day in enumerate(order):
        if day in days or i == 0:
            continue
        before = days.get(order[i - 1])
        after = next((days[d] for d in order[i + 1:] if d in days), None)
        if before is None:
            continue
        if after is not None:
            x = (before["x"] + after["x"]) / 2
        else:
            earlier = days.get(order[i - 2]) if i >= 2 else None
            if earlier is None:
                continue
            x = before["x"] + (before["x"] - earlier["x"])
        days[day] = {"text": day, "x": x, "left": x, "right": x, "y": before["y"], "top": before["top"],
                     "bottom": before["bottom"], "h": before["h"]}


def _timetable_lines(boxes: list[dict]) -> list[str] | None:
    """Rebuild a weekly grid as "Day time: text" lines, or None if this isn't a time table."""
    days = {}
    for box in boxes:
        low = box["text"].lower()
        for day in WEEKDAYS:
            if low.endswith(day) and day not in days:  # "Time/Day" can share a box with Monday
                days[day] = box
    if len(days) < 4:
        return None
    _fill_missing_days(days)
    columns = sorted(days.items(), key=lambda kv: kv[1]["x"])
    header_y = max(b["bottom"] for _, b in columns)
    first_left = columns[0][1]["left"]
    # Column edges sit halfway between neighbouring day labels.
    edges = [(a[1]["x"] + b[1]["x"]) / 2 for a, b in zip(columns, columns[1:])]

    # The first column holds times, often split over two boxes ("08.00-" / "08.55").
    left_col = sorted((b for b in boxes if b["y"] > header_y and b["x"] < first_left), key=lambda b: b["y"])
    slots: list[dict] = []
    for box in left_col:
        if not TIME_RE.match(box["text"]):
            continue
        if slots and slots[-1]["label"].endswith("-"):
            slots[-1]["label"] += box["text"]
        elif slots and "-" not in slots[-1]["label"]:
            slots[-1]["label"] += "-" + box["text"]
        else:
            slots.append({"label": box["text"], "y": box["top"]})
    if len(slots) < 3:
        return None

    cells: dict[tuple[int, int], list[dict]] = {}
    above = []
    for box in boxes:
        if box["y"] <= header_y:
            if box not in [b for _, b in columns]:
                above.append(box)
            continue
        if box["x"] < first_left:
            continue
        row = max((i for i, s in enumerate(slots) if box["y"] >= s["y"] - box["h"] * 0.5), default=None)
        if row is None:
            continue
        col = sum(box["x"] > edge for edge in edges)
        cells.setdefault((row, col), []).append(box)

    lines = _reading_order(above)
    lunch = None
    for col, (day, _) in enumerate(columns):
        lines.append(f"## {day.capitalize()}")
        for row, slot in enumerate(slots):
            parts = cells.get((row, col))
            if parts:
                text = _tidy_cell(" ".join(" ".join(ln.split(" | ")) for ln in _reading_order(parts)))
                if text.upper() == "LUNCH":  # a merged cell across all days
                    lunch = f"All days {slot['label']}: LUNCH"
                else:
                    lines.append(f"{day.capitalize()} {slot['label']}: {text}")
    if lunch:
        lines.append(lunch)
    return lines


def _tidy_cell(text: str) -> str:
    """Undo OCR's usual damage to time-table entries; codes and rooms have a fixed shape."""
    text = re.sub(r"\b([A-Z]{2})l-", r"\1I-", text)  # MAl-101 -> MAI-101 (lower-case L for I)
    text = re.sub(r"\b([LTP]) ?([A-Z]{3})- ?(\d{3})", r"\1 \2-\3", text)  # LECC-101 -> L ECC-101
    text = re.sub(r"(-\d{3})(?=\d{2}[A-Z]{2}\d|[A-Z])", r"\1 ", text)  # HSI-10126EC1 -> HSI-101 26EC1
    text = re.sub(r"(\d{2}[A-Z]{2}\d)(?=[A-Z])", r"\1 ", text)  # 26EC1APJ -> 26EC1 APJ
    text = re.sub(r"(?<=[a-z])(?=\d{2}[A-Z]{2}\d)", " ", text)  # Mahapatra26EC1 -> Mahapatra 26EC1
    text = text.replace("APJAKB", "APJ AKB").replace("AKB- ", "AKB-")
    text = re.sub(r"(AKB-\d{3}|GB-\d{3})(?=[A-Z])", r"\1 ", text)  # AKB-603Aruni -> AKB-603 Aruni
    return re.sub(r"Batch ?(\d)", r"Batch \1 ", text).replace("  ", " ").strip()


def _ocr_page(page) -> list[str]:
    boxes = _boxes(page.render(scale=RENDER_SCALE).to_pil())
    return _timetable_lines(boxes) or _reading_order(boxes)


def _ocr_pdf(data: bytes, page_numbers: list[int]) -> dict[int, list[str]]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    return {n: _ocr_page(pdf[n]) for n in page_numbers[:MAX_OCR_PAGES]}


TIMETABLE_HEADING = re.compile(r"TIME\s*TABLE\s*\|\s*(\S+?)-Year-\((.+)", re.I)
TIMETABLE_PROGRAMMES = (
    ("B.Tech", "B.Tech ECE"), ("Network", "M.Tech CNSP"), ("R.F", "M.Tech RF"), ("VLSI", "M.Tech VLSI"),
    ("Terahertz", "M.Tech THz"), ("Semiconductor", "M.Tech Semiconductor"),
)


def label_timetable_rows(text: str) -> str:
    """Prefix time-table rows with their programme and year ("B.Tech ECE Year III | Tuesday ...").

    One PDF holds a page per year or programme, whatever its file name says, and each
    page states which one only in its heading.
    """
    label = ""
    out = []
    for line in text.splitlines():
        heading = TIMETABLE_HEADING.search(line)
        if heading:
            year = heading.group(1).replace("l", "I").upper()  # OCR reads "III" as "Ill"
            programme = next((short for key, short in TIMETABLE_PROGRAMMES if key in heading.group(2)), "")
            label = f"{programme or clean(heading.group(2))} Year {year}"
        elif label and re.match(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|All days)\b", line):
            line = f"{label} | {line}"
        out.append(line)
    return "\n".join(out)


def label_structure_rows(text: str) -> str:
    """Prefix teaching-scheme rows with their year and semester ("Year I Autumn: 4 ECC-101 ...").

    Those headings are only stated once per table, so chunks cut from the middle lose them.
    """
    section = ""
    out = []
    for line in text.splitlines():
        heading = re.match(r"Year\s*:[\s|]*(\S+)\s*$", line)
        term = re.search(r"\((Autumn|Spring)\)\s*$", line)
        if heading:
            section = f"Year {heading.group(1)}"
        elif term and section.startswith("Year"):
            section = f"{' '.join(section.split()[:2])} {term.group(1)}"
        elif re.match(r"List of .*Elective", line, re.I):
            section = "Elective list"  # not part of the year it happens to follow
        elif section and re.match(r"(?:\d+\.?\s+)?[A-Z]{2,4}\s*-\s*\d{3}", line):
            line = f"{section}: {line}"
        out.append(line)
    return "\n".join(out)


def extract_pdf(data: bytes) -> tuple[str, bool]:
    """Return (text, mostly_scanned). Text is whole-document; scanned pages are OCRed."""
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    pages: list[str] = []
    for page in reader.pages[:MAX_TEXT_PAGES]:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # malformed pages are common in scanned adverts
            pages.append("")
    scanned = [i for i, text in enumerate(pages) if len(text.strip()) < MIN_PAGE_CHARS]

    ocr_text: dict[int, str] = {}
    if scanned:
        digest = hashlib.sha256(data).hexdigest()
        cache = CACHE_DIR / f"{digest}.txt"
        if cache.exists():
            for i, blob in enumerate(cache.read_text(encoding="utf-8").split("\f")):
                if blob.strip():
                    ocr_text[i] = blob
        else:
            try:
                for i, lines in _ocr_pdf(data, scanned).items():
                    ocr_text[i] = "\n".join(lines)
            except Exception:
                log.exception("OCR failed")
            if ocr_text:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                last = max(ocr_text)
                cache.write_text("\f".join(ocr_text.get(i, "") for i in range(last + 1)), encoding="utf-8")

    out: list[str] = []
    for i, text in enumerate(pages):
        body = ocr_text.get(i, text)
        for line in body.splitlines():
            line = line.strip() if line.startswith("## ") else clean(line)
            if line:
                out.append(line)
    # Many syllabus PDFs are text with a few scanned pages; only warn about mostly-scanned ones.
    return label_timetable_rows(label_structure_rows("\n".join(out))), len(ocr_text) >= max(1, len(pages) / 2)
