"""Embeds a query and retrieves top-k chunks, hybrid dense+sparse.

Dispatches to Postgres/pgvector (shore-side, config.STORAGE_BACKEND="postgres",
the default) or to the single-file SQLite/sqlite-vec snapshot (vessel-side,
STORAGE_BACKEND="sqlite" — see README "Shipboard deployment"). Both fuse dense
cosine search with sparse keyword search via Reciprocal Rank Fusion, the
pattern used for maritime accident-report retrieval in the Multi-Field Hybrid
RAG paper (arXiv 2606.13249).
"""
import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector

from config import DATABASE_URL, STORAGE_BACKEND
from ingest.embed import embed_query
from retrieval.diversify import select as _diversify_select
from retrieval.rerank import rerank as _cross_encoder_rerank


def _retrieve_postgres(query: str, top_k: int, fetch_k: int, rrf_k: int) -> list[dict]:
    query_embedding = Vector(embed_query(query))
    with psycopg.connect(DATABASE_URL) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM chunks ORDER BY embedding <=> %s LIMIT %s",
                (query_embedding, fetch_k),
            )
            dense_rank = {row[0]: i for i, row in enumerate(cur.fetchall())}

            cur.execute(
                """
                SELECT id FROM chunks
                WHERE content_tsv @@ plainto_tsquery('english', %s)
                ORDER BY ts_rank(content_tsv, plainto_tsquery('english', %s)) DESC
                LIMIT %s
                """,
                (query, query, fetch_k),
            )
            sparse_rank = {row[0]: i for i, row in enumerate(cur.fetchall())}

            fused: dict[int, float] = {}
            for chunk_id, rank in dense_rank.items():
                fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (rrf_k + rank)
            for chunk_id, rank in sparse_rank.items():
                fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (rrf_k + rank)
            if not fused:
                return []
            top_ids = sorted(fused, key=fused.get, reverse=True)[:top_k]

            cur.execute(
                """
                SELECT c.id, c.content, d.title, d.url, d.source
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE c.id = ANY(%s)
                """,
                (top_ids,),
            )
            by_id = {r[0]: r for r in cur.fetchall()}
    return [
        {
            "content": by_id[i][1],
            "title": by_id[i][2],
            "url": by_id[i][3],
            "source": by_id[i][4],
            "score": fused[i],
        }
        for i in top_ids
        if i in by_id
    ]


def retrieve(
    query: str,
    top_k: int = 5,
    fetch_k: int = 30,
    rrf_k: int = 60,
    rerank: bool = True,
    candidate_k: int = 20,
) -> list[dict]:
    """RRF gives a fused pool ranked by *where* each side placed a chunk, not
    by how relevant it actually is to the query, and says nothing about
    whether two chunks are redundant — so pull a wider candidate_k pool from
    RRF regardless of rerank, let the cross-encoder rescore it (if enabled),
    then let diversify.select() do the final top_k cut, skipping same-source
    overflow and near-duplicates as it walks down the ranking."""
    pool_k = max(top_k, candidate_k)
    if STORAGE_BACKEND == "sqlite":
        from retrieval import sqlite_store

        candidates = sqlite_store.retrieve(query, embed_query(query), pool_k, fetch_k, rrf_k)
    else:
        candidates = _retrieve_postgres(query, pool_k, fetch_k, rrf_k)

    if rerank:
        candidates = _cross_encoder_rerank(query, candidates)
    return _diversify_select(candidates, top_k)
