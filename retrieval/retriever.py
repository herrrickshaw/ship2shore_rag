"""Embeds a query and retrieves top-k chunks, hybrid dense+sparse.

Dispatches to Postgres/pgvector (shore-side, config.STORAGE_BACKEND="postgres",
the default) or to the single-file SQLite/sqlite-vec snapshot (vessel-side,
STORAGE_BACKEND="sqlite" — see README "Shipboard deployment"). Both fuse dense
cosine search with sparse keyword search via Reciprocal Rank Fusion, the
pattern used for maritime accident-report retrieval in the Multi-Field Hybrid
RAG paper (arXiv 2606.13249).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector

from config import DATABASE_URL, STORAGE_BACKEND
from ingest.embed import embed_query
from retrieval.diversify import select as _diversify_select
from retrieval.fusion import rrf_fuse, top_ids
from retrieval.rerank import rerank as _cross_encoder_rerank

# Injection seams: the embedder, reranker and storage backend are plain callables so
# tests (and alternative deployments) can swap them without importing heavy ML deps.
QueryEmbedder = Callable[[str], "list[float]"]
Reranker = Callable[[str, "list[dict]"], "list[dict]"]
Backend = Callable[[str, int, int, int], "list[dict]"]  # (query, top_k, fetch_k, rrf_k)


def _retrieve_postgres(
    query: str,
    top_k: int,
    fetch_k: int,
    rrf_k: int,
    embed: QueryEmbedder | None = None,
    connect: Callable[..., Any] | None = None,
) -> list[dict]:
    """Hybrid dense+sparse retrieval against Postgres; embed/connect default to the real ones."""
    query_embedding = Vector((embed or embed_query)(query))
    with (connect or psycopg.connect)(DATABASE_URL) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            # ivfflat defaults to probes=1, i.e. searching only 1 of the
            # index's 100 lists (db/schema.sql) -- ~1% of the table. At this
            # corpus's scale (18k+ chunks) that silently drops true nearest
            # neighbours from genuinely relevant documents in favor of
            # whatever happens to land in the single probed list. probes=10
            # (~sqrt(lists), the standard pgvector recall/latency tradeoff)
            # was confirmed live to recover matches this missed entirely.
            # SET LOCAL scopes it to this transaction only.
            cur.execute("SET LOCAL ivfflat.probes = 10")
            cur.execute(
                "SELECT id FROM chunks ORDER BY embedding <=> %s LIMIT %s",
                (query_embedding, fetch_k),
            )
            dense_ids = [row[0] for row in cur.fetchall()]

            cur.execute(
                """
                SELECT id FROM chunks
                WHERE content_tsv @@ plainto_tsquery('english', %s)
                ORDER BY ts_rank(content_tsv, plainto_tsquery('english', %s)) DESC
                LIMIT %s
                """,
                (query, query, fetch_k),
            )
            sparse_ids = [row[0] for row in cur.fetchall()]

            fused = rrf_fuse(dense_ids, sparse_ids, rrf_k)
            if not fused:
                return []
            ranked_ids = top_ids(fused, top_k)

            cur.execute(
                """
                SELECT c.id, c.content, d.title, d.url, d.source, d.published_at, c.regulation_refs
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE c.id = ANY(%s)
                """,
                (ranked_ids,),
            )
            by_id = {r[0]: r for r in cur.fetchall()}
    return [
        {
            "content": by_id[i][1],
            "title": by_id[i][2],
            "url": by_id[i][3],
            "source": by_id[i][4],
            "published_at": by_id[i][5],
            "regulation_refs": by_id[i][6],
            "score": fused[i],
        }
        for i in ranked_ids
        if i in by_id
    ]


def _passage_date(published_at: Any) -> date | None:
    if published_at is None:
        return None
    if isinstance(published_at, datetime):
        return published_at.date()
    if isinstance(published_at, date):
        return published_at
    return datetime.fromisoformat(str(published_at).replace("Z", "+00:00")).date()


def _apply_filters(
    candidates: list[dict], since: date | None, source_filter: str | None
) -> list[dict]:
    """Post-filter: simplest correct implementation, applied after content is
    already joined in. RRF/fetch_k don't know about these filters, so an
    aggressive since/source_filter can shrink the candidate pool below
    top_k — push-down filtering (adding the WHERE clause to the RRF queries
    themselves) is the fix if that turns out to matter in practice."""
    if source_filter is not None:
        candidates = [p for p in candidates if p.get("source") == source_filter]
    if since is not None:
        candidates = [
            p for p in candidates if (_passage_date(p.get("published_at")) or date.min) >= since
        ]
    return candidates


def retrieve(
    query: str,
    top_k: int = 5,
    fetch_k: int = 30,
    rrf_k: int = 60,
    rerank: bool = True,
    candidate_k: int = 20,
    since: date | None = None,
    source_filter: str | None = None,
    embed: QueryEmbedder | None = None,
    reranker: Reranker | None = None,
    backend: Backend | None = None,
) -> list[dict]:
    """embed/reranker/backend default to the real implementations (see module seams).

    RRF gives a fused pool ranked by *where* each side placed a chunk, not
    by how relevant it actually is to the query, and says nothing about
    whether two chunks are redundant — so pull a wider candidate_k pool from
    RRF regardless of rerank, let the cross-encoder rescore it (if enabled),
    then let diversify.select() do the final top_k cut, skipping same-source
    overflow and near-duplicates as it walks down the ranking. since/
    source_filter narrow the pool before any of that (see _apply_filters)."""
    pool_k = max(top_k, candidate_k)
    if backend is not None:
        candidates = backend(query, pool_k, fetch_k, rrf_k)
    elif STORAGE_BACKEND == "sqlite":
        from retrieval import sqlite_store

        candidates = sqlite_store.retrieve(
            query, (embed or embed_query)(query), pool_k, fetch_k, rrf_k
        )
    else:
        candidates = _retrieve_postgres(query, pool_k, fetch_k, rrf_k, embed=embed)

    candidates = _apply_filters(candidates, since, source_filter)

    if rerank:
        candidates = (reranker or _cross_encoder_rerank)(query, candidates)
    return _diversify_select(candidates, top_k)
