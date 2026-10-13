"""Hybrid index: Chroma (dense vectors) + SQLite FTS5 (BM25 keywords).

Dense search handles paraphrase ("who works on chips" -> VLSI); BM25 handles
exact tokens that embeddings blur (names, "SERB", "6G", course codes). The two
rankings are merged with reciprocal-rank fusion.
"""

import re
import threading
from dataclasses import dataclass

import chromadb
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import CHROMA_DIR
from app.db.database import engine
from app.rag.embeddings import embed_passages, embed_query

COLLECTION = "ece_chunks"
RRF_K = 60

_client = None
_lock = threading.Lock()


def collection():
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})


@dataclass
class Hit:
    chunk_id: str
    text: str
    title: str
    url: str
    category: str
    score: float


# ---------------------------------------------------------------------------
# Writes (called by the ingestion pipeline)
# ---------------------------------------------------------------------------


def index_chunks(db: Session, rows: list[dict]):
    """rows: {id, text (with header), title, heading, body, url, category, page_id}.

    FTS writes go through the caller's session so they share its transaction
    (a second SQLite connection would block on the session's write lock).
    """
    if not rows:
        return
    col = collection()
    for start in range(0, len(rows), 64):
        batch = rows[start:start + 64]
        col.upsert(
            ids=[r["id"] for r in batch],
            embeddings=embed_passages([r["text"] for r in batch]),
            documents=[r["text"] for r in batch],
            metadatas=[{"page_id": r["page_id"], "url": r["url"], "title": r["title"],
                        "category": r["category"]} for r in batch],
        )
    db.execute(text("DELETE FROM chunks_fts WHERE chunk_id = :id"), [{"id": r["id"]} for r in rows])
    db.execute(
        text("INSERT INTO chunks_fts (chunk_id, title, heading, body) VALUES (:id, :title, :heading, :body)"),
        [{"id": r["id"], "title": r["title"], "heading": r["heading"], "body": r["body"]} for r in rows],
    )


def delete_page_chunks(db: Session, page_id: int):
    collection().delete(where={"page_id": page_id})
    db.execute(text("DELETE FROM chunks_fts WHERE chunk_id LIKE :p"), {"p": f"{page_id}:%"})


def count() -> int:
    return collection().count()


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

STOPWORDS = set("""a an and are as at be by can do does for from has have how i in is it
me my of on or tell the their there this to was what when where which who whom why
will with you your about any some please list show give find all""".split())


def _fts_query(query: str) -> str | None:
    terms = [t for t in re.findall(r"[A-Za-z0-9]+", query.lower()) if t not in STOPWORDS and len(t) > 1]
    if not terms:
        return None
    return " OR ".join(f'"{t}"' for t in dict.fromkeys(terms))


def _dense(query: str, n: int, category: str | None) -> list[Hit]:
    col = collection()
    if col.count() == 0:
        return []
    res = col.query(
        query_embeddings=[embed_query(query)], n_results=n,
        where={"category": category} if category else None,
    )
    hits = []
    for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
        hits.append(Hit(cid, doc, meta["title"], meta["url"], meta["category"], 1 - dist))
    return hits


def _keyword(query: str, n: int, category: str | None) -> list[Hit]:
    fts = _fts_query(query)
    if not fts:
        return []
    sql = (
        "SELECT f.chunk_id, p.title, p.url, p.category, c.heading, c.text, bm25(chunks_fts, 0, 2.0, 1.5, 1.0) AS s "
        "FROM chunks_fts f JOIN chunks c ON c.id = f.chunk_id JOIN pages p ON p.id = c.page_id "
        "WHERE chunks_fts MATCH :q AND p.active = 1 "
        + ("AND p.category = :cat " if category else "")
        + "ORDER BY s LIMIT :n"
    )
    with engine.connect() as conn:
        rows = conn.execute(text(sql), {"q": fts, "n": n, "cat": category}).fetchall()
    hits = []
    for cid, title, url, cat, heading, body, score in rows:
        header = f"{title} > {heading}" if heading else title
        hits.append(Hit(cid, f"{header}\n{body}", title, url, cat, -score))
    return hits


def search(query: str, k: int = 6, category: str | None = None) -> list[Hit]:
    dense = _dense(query, 20, category)
    keyword = _keyword(query, 20, category)
    fused: dict[str, float] = {}
    by_id: dict[str, Hit] = {}
    for ranking in (dense, keyword):
        for rank, hit in enumerate(ranking):
            fused[hit.chunk_id] = fused.get(hit.chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
            by_id.setdefault(hit.chunk_id, hit)
    ordered = sorted(fused, key=fused.get, reverse=True)
    results = []
    per_page: dict[str, int] = {}
    for cid in ordered:
        hit = by_id[cid]
        # Diversity: at most 3 chunks from a single page.
        if per_page.get(hit.url, 0) >= 3:
            continue
        per_page[hit.url] = per_page.get(hit.url, 0) + 1
        hit.score = fused[cid]
        results.append(hit)
        if len(results) >= k:
            break
    return results
