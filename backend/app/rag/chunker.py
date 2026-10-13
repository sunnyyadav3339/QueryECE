"""Split heading-structured page text into retrieval chunks.

Each chunk is prefixed with "<page title> > <heading>" so it stays
self-describing once it is pulled out of the page (contextual chunk headers).
"""

from dataclasses import dataclass

MAX_CHARS = 1200  # ~300 tokens: small enough to pack 6-8 chunks in the budget
OVERLAP_LINES = 1


@dataclass
class TextChunk:
    heading: str
    text: str  # body without the contextual header
    header: str  # "Title > Heading"

    @property
    def full_text(self) -> str:
        return f"{self.header}\n{self.text}"


def _split_long_line(line: str) -> list[str]:
    if len(line) <= MAX_CHARS:
        return [line]
    parts, current = [], ""
    for sentence in line.replace(". ", ".\n").split("\n"):
        if current and len(current) + len(sentence) + 1 > MAX_CHARS:
            parts.append(current)
            current = ""
        current = f"{current} {sentence}".strip()
        while len(current) > MAX_CHARS:  # no sentence boundaries at all
            parts.append(current[:MAX_CHARS])
            current = current[MAX_CHARS:]
    if current:
        parts.append(current)
    return parts


def chunk_page(title: str, text: str) -> list[TextChunk]:
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif line.strip():
            sections[-1][1].extend(_split_long_line(line.strip()))

    chunks: list[TextChunk] = []
    pending_heading = ""
    for heading, lines in sections:
        if not lines:
            # Consecutive headings ("BioSketch" then "Educational Details"):
            # carry the parent forward so the context isn't lost.
            pending_heading = f"{pending_heading} > {heading}".strip(" >") if heading else pending_heading
            continue
        full_heading = f"{pending_heading} > {heading}".strip(" >") if pending_heading else heading
        pending_heading = ""
        header = f"{title} > {full_heading}" if full_heading else title

        current: list[str] = []
        size = 0
        for line in lines:
            if current and size + len(line) > MAX_CHARS:
                chunks.append(TextChunk(full_heading, "\n".join(current), header))
                current = current[-OVERLAP_LINES:] if len(current[-1]) < MAX_CHARS // 3 else []
                size = sum(len(x) for x in current)
            current.append(line)
            size += len(line)
        if current:
            chunks.append(TextChunk(full_heading, "\n".join(current), header))

    # Drop near-empty chunks (stray labels) unless the page has nothing else.
    meaningful = [c for c in chunks if len(c.text) >= 40]
    return meaningful or chunks
