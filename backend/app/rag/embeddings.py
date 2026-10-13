"""Local, free sentence embeddings via fastembed (ONNX; no torch, CPU-only).

BAAI/bge-small-en-v1.5: 384-dim, ~130 MB, downloaded once from Hugging Face
into data/models and reused afterwards.
"""

import threading

import numpy as np

from app.config import EMBED_MODEL, MODEL_CACHE_DIR

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from fastembed import TextEmbedding

                _model = TextEmbedding(model_name=EMBED_MODEL, cache_dir=str(MODEL_CACHE_DIR))
    return _model


def embed_passages(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return [v.tolist() for v in _get_model().passage_embed(texts, batch_size=32)]


def embed_query(text: str) -> list[float]:
    # query_embed adds bge's "Represent this sentence for searching..." prefix.
    return next(iter(_get_model().query_embed(text))).tolist()


def cosine(a, b) -> float:
    a, b = np.asarray(a), np.asarray(b)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
    return float(a @ b) / denom
