"""Keep lists of named applicants out of the index.

Admission notices publish selection lists ("S.NO. Deptt. Appl. No Full Name
Scheme", one row per candidate) so applicants can find themselves. Indexed, they
would let anyone ask the assistant about a named person, so the rows are
replaced by a count while the notice itself (title, programme, instructions,
links) stays searchable. The linked PDF remains the place to check a name.

The crawler's file-name filter (crawler.APPLICANT_LIST) misses most of these,
since they are named after the department ("ECD.pdf"), so this looks at the text.
"""

import re
from collections import Counter

# Wording of a list of candidates, as opposed to rules about candidates.
LIST_SIGNAL = re.compile(
    r"provisionally\s+selected|selected\s+candidates|candidates\s+(?:provisionally\s+)?selected|"
    r"list\s+of\s+(?:the\s+)?(?:selected|shortlisted|eligible|candidates|applicants)|"
    r"short-?listed\s+(?:candidates|for)|wait\s*-?\s*list|merit\s*-?\s*list",
    re.I,
)
# Column header of such a list: an application/roll/registration number column
# ("S.NO. Deptt. Appl. No Full Name Scheme", "Appl.No COAPID GATE reg No.").
HEADER = re.compile(
    r"\b(?:appl(?:ication)?\.?\s*(?:no|number|id)|roll\s*no|registration\s*no|reg\.?\s*no|"
    r"enrol(?:l)?ment\s*no|form\s*no|coap\s*id)\b",
    re.I,
)
# One candidate: serial number, then an application id with at least 5 digits
# ("1 ECDA26011065 <name> ..."; OCR may put " | " between columns), or a line of
# ids alone ("MTECH26000004 COAP26008155 26S73012024").
ROW = re.compile(
    r"^\s*\d{1,4}[.)]?(?:\s+|\s*\|\s*)(?:[A-Z]{1,8}\s*)?[A-Z]{0,8}\d{5,}[A-Z0-9/-]*\b"
    r"|^\s*(?:[A-Za-z0-9]*\d{6,}[A-Za-z0-9]*\s+){1,4}[A-Za-z0-9]*\d{6,}[A-Za-z0-9]*\s*$",
    re.M,
)
NAME_COLUMN = re.compile(r"\bname\b", re.I)
# Funding schemes printed in the rows; only these words are kept, never the name.
SCHEMES = {
    "Institute Assistantship": r"institute\s+assistantship",
    "In Service - External": r"in\s*-?\s*service\s*[-–]\s*external",
    "In Service - Internal": r"in\s*-?\s*service\s*[-–]\s*internal",
    "Sponsored": r"\bsponsored\b",
    "Self Financed": r"self\s*-?\s*financ",
    "Project": r"\bproject\b",
    "Fellowship (CSIR/UGC/other)": r"\b(?:csir|ugc|fellowship|jrf)\b",
    "Part Time": r"part\s*-?\s*time",
}
NOTE = "[Names and application numbers of individual candidates are omitted here; the linked document has the full list.]"


def redact_applicant_lists(text: str) -> str:
    """Replace candidate rows with a count; return text unchanged when it isn't such a list."""
    if not text or not LIST_SIGNAL.search(text):
        return text
    lines = text.splitlines()
    header_idx = [i for i, line in enumerate(lines) if HEADER.search(line)]
    row_idx = [i for i, line in enumerate(lines) if ROW.match(line)]
    # A list needs the list wording above, a number column header and id rows: one is
    # enough under a name column (a centre may select a single candidate), otherwise
    # three, so a brochure line like "(c) Application No." can't trigger it.
    named = any(NAME_COLUMN.search(lines[i]) for i in header_idx)
    if not header_idx or len(row_idx) < (1 if named else 3):
        return text

    drop = set(header_idx) | set(row_idx)
    schemes = Counter()
    for i in row_idx:
        for label, pattern in SCHEMES.items():
            if re.search(pattern, lines[i], re.I):
                schemes[label] += 1
                break
    summary = f"Candidates listed: {len(row_idx)}"
    if schemes:
        summary += " (by scheme: " + ", ".join(f"{k} {v}" for k, v in schemes.most_common()) + ")"

    out, placed = [], False
    for i, line in enumerate(lines):
        if i in drop:
            if not placed:
                out += [summary, NOTE]
                placed = True
            continue
        out.append(line)
    return "\n".join(out)
