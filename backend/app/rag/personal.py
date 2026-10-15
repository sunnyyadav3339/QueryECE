"""Match a student's interests to faculty, with a reason for each match.

Similarities measured with bge-small on this data: a student interest vs. the
right professor's interest list ~0.70-0.82, vs. an unrelated one ~0.50-0.60.
"""

import re
import threading

from app.db.models import Faculty
from app.rag.embeddings import cosine, embed_passages, embed_query

SCORE_FLOOR, SCORE_CEIL = 0.60, 0.82  # -> 0% .. 100%
MATCH_THRESHOLD = 0.68  # an interest counts as "matched" at or above this
TOPIC_THRESHOLD = 0.72  # a specific faculty topic is shown as the reason at or above this

_lock = threading.Lock()
_profile_vecs: dict[tuple[int, str], list[float]] = {}
_topic_vecs: dict[str, list[float]] = {}
_query_vecs: dict[str, list[float]] = {}


def _topics(interests: str | None) -> list[str]:
    parts = re.split(r"\s*[,;]\s*", interests or "")
    return [p.strip() for p in parts if 3 <= len(p.strip()) <= 120]


def _ensure_vectors(faculty: list[Faculty], interests: list[str]):
    """Embed anything not cached yet (faculty text changes only when the crawler updates it)."""
    with _lock:
        missing = [f for f in faculty if (f.id, f.interests or "") not in _profile_vecs]
        if missing:
            vecs = embed_passages([f"{f.name}: {f.interests or f.designation or ''}" for f in missing])
            for f, v in zip(missing, vecs):
                _profile_vecs[(f.id, f.interests or "")] = v
        topics = {t for f in faculty for t in _topics(f.interests)} - _topic_vecs.keys()
        if topics:
            topics = sorted(topics)
            _topic_vecs.update(zip(topics, embed_passages(topics)))
        for i in interests:
            if i not in _query_vecs:
                _query_vecs[i] = embed_query(i)


def percent(score: float) -> int:
    return max(0, min(99, round((score - SCORE_FLOOR) / (SCORE_CEIL - SCORE_FLOOR) * 100)))


def rank_faculty(faculty: list[Faculty], interests: list[str]) -> list[dict]:
    """Every faculty member with match %, matched student interests and the reason topics.

    Sorted best first. With no interests, everyone scores 0 and keeps the input order.
    """
    interests = [i for i in interests if i.strip()]
    if not interests or not faculty:
        return [{"faculty": f, "match": 0, "matched": [], "reasons": []} for f in faculty]
    _ensure_vectors(faculty, interests)

    out = []
    for f in faculty:
        fv = _profile_vecs[(f.id, f.interests or "")]
        sims = sorted(((cosine(_query_vecs[i], fv), i) for i in interests), reverse=True)
        best = sims[0][0]
        # A second matching interest nudges the score up: broader overlap.
        bonus = 0.25 * max(0.0, sims[1][0] - MATCH_THRESHOLD) if len(sims) > 1 else 0.0
        matched = [i for s, i in sims if s >= MATCH_THRESHOLD]
        reasons = []
        for i in matched[:3]:
            topic_scores = [(cosine(_query_vecs[i], _topic_vecs[t]), t) for t in _topics(f.interests)]
            if topic_scores:
                s, t = max(topic_scores)
                if s >= TOPIC_THRESHOLD:
                    reasons.append({"interest": i, "topic": t})
        out.append({"faculty": f, "match": percent(best + bonus), "matched": matched, "reasons": reasons})
    out.sort(key=lambda r: -r["match"])
    return out


def top_matches(faculty: list[Faculty], interests: list[str], top: int = 6, min_match: int = 35) -> list[dict]:
    """Best matches that cover every interest: the top two per interest first, then by
    overall score, so one dominant interest doesn't crowd out the others."""
    ranked = [r for r in rank_faculty(faculty, interests) if r["match"] >= min_match] if interests else []
    picked: list[dict] = []
    for interest in interests:
        for r in [r for r in ranked if interest in r["matched"]][:2]:
            if r not in picked:
                picked.append(r)
    picked += [r for r in ranked if r not in picked]
    return sorted(picked[:top], key=lambda r: -r["match"])


def profile_matches_text(faculty: list[Faculty], interests: list[str], top: int = 6) -> str:
    """Compact list for the agent's system prompt."""
    lines = []
    for r in top_matches(faculty, interests, top):
        f = r["faculty"]
        why = "; ".join(f"{x['interest']} ↔ {x['topic']}" for x in r["reasons"]) or ", ".join(r["matched"])
        lines.append(f"- Prof. {f.name} ({r['match']}% match{': ' + why if why else ''})")
    return "\n".join(lines)
