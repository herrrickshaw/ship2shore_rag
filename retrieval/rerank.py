"""Cross-encoder reranking of the RRF-fused candidate pool.

RRF (retriever.py) fuses two independent rankings (dense cosine + sparse
keyword) but never scores a candidate against the query directly — it only
knows *where* each side ranked it. A cross-encoder reads (query, passage)
pairs jointly and scores relevance directly, which is normally where the
single biggest relevance gain in a hybrid pipeline comes from. Local, no API
key — same sentence-transformers dependency already used for embeddings,
just its CrossEncoder class instead of SentenceTransformer.
"""
from functools import lru_cache

from config import RERANKER_MODEL


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(RERANKER_MODEL)


def rerank(query: str, passages: list[dict], top_k: int) -> list[dict]:
    """Rescore passages against the query and return the best top_k, each
    tagged with rerank_score. passages must have a 'content' key."""
    if not passages:
        return []
    pairs = [(query, p["content"]) for p in passages]
    scores = _model().predict(pairs)
    for p, score in zip(passages, scores):
        p["rerank_score"] = float(score)
    return sorted(passages, key=lambda p: p["rerank_score"], reverse=True)[:top_k]
