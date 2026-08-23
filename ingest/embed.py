"""Local embeddings via sentence-transformers — no API key, no per-call cost."""
from functools import lru_cache

from config import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return _model().encode(texts, show_progress_bar=False, normalize_embeddings=True).tolist()


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
