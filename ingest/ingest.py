"""Orchestrates fetch -> chunk -> embed -> upsert into pgvector or sqlite.

Dispatches on config.STORAGE_BACKEND, same pattern as retrieval/retriever.py.
Re-ingesting an already-seen URL compares content_hash: unchanged content is
skipped (previous behavior, never re-chunked); changed content replaces the
document's chunks in place instead of being silently skipped or duplicated.
"""

from __future__ import annotations

from typing import Callable

import psycopg
from pgvector.psycopg import register_vector
from psycopg.types.json import Json

from config import DATABASE_URL, STORAGE_BACKEND
from ingest.chunk import chunk_text
from ingest.embed import embed_texts
from ingest.freshness import compute_hash
from ingest.regulation_refs import extract_refs

Embedder = Callable[["list[str]"], "list[list[float]]"]  # injection seam for embeddings


def _prepare_chunks(
    text: str, embed: Embedder | None
) -> tuple[list[str], list[list[float]], list[list[dict]]]:
    """Chunk text, embed each chunk, and extract regulation refs per chunk.

    Returns ([], [], []) when the text yields no chunks (embedder is not called).
    """
    chunks = chunk_text(text)
    if not chunks:
        return [], [], []
    embeddings = (embed or embed_texts)(chunks)
    return chunks, embeddings, [extract_refs(chunk) for chunk in chunks]


def ingest_documents(
    documents: list[dict], sqlite_path: str | None = None, embed: Embedder | None = None
) -> int:
    """Upserts documents + their chunks/embeddings. Returns count of documents
    ingested or updated in place (documents already present by URL whose
    content_hash is unchanged are skipped, not re-embedded).

    sqlite_path overrides SQLITE_PATH when STORAGE_BACKEND == "sqlite" —
    unused otherwise (kept optional so cli.py's existing ingest_documents(docs)
    call site needs no change). embed overrides the local sentence-transformers embedder."""
    if STORAGE_BACKEND == "sqlite":
        return _ingest_sqlite(documents, sqlite_path, embed)
    return _ingest_postgres(documents, embed)


def _ingest_postgres(documents: list[dict], embed: Embedder | None = None) -> int:
    changed = 0
    with psycopg.connect(DATABASE_URL, autocommit=False) as conn:
        register_vector(conn)
        for doc in documents:
            content_hash = compute_hash(doc["text"])
            with conn.cursor() as cur:
                cur.execute("SELECT id, content_hash FROM documents WHERE url = %s", (doc["url"],))
                existing = cur.fetchone()
                if existing and existing[1] == content_hash:
                    continue

                chunks, embeddings, refs_per_chunk = _prepare_chunks(doc["text"], embed)
                if not chunks:
                    continue

                if existing:
                    doc_id = existing[0]
                    cur.execute("DELETE FROM chunks WHERE document_id = %s", (doc_id,))
                    cur.execute(
                        "UPDATE documents SET title = %s, license = %s, published_at = %s, "
                        "content_hash = %s WHERE id = %s",
                        (
                            doc["title"],
                            doc.get("license"),
                            doc.get("published_at"),
                            content_hash,
                            doc_id,
                        ),
                    )
                else:
                    cur.execute(
                        "INSERT INTO documents (source, url, title, license, published_at, content_hash) "
                        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                        (
                            doc["source"],
                            doc["url"],
                            doc["title"],
                            doc.get("license"),
                            doc.get("published_at"),
                            content_hash,
                        ),
                    )
                    doc_id = cur.fetchone()[0]

                cur.executemany(
                    "INSERT INTO chunks (document_id, chunk_index, content, embedding, regulation_refs) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    [
                        (doc_id, i, chunk, embedding, Json(refs))
                        for i, (chunk, embedding, refs) in enumerate(
                            zip(chunks, embeddings, refs_per_chunk)
                        )
                    ],
                )
            conn.commit()
            changed += 1
    return changed


def _ingest_sqlite(
    documents: list[dict], sqlite_path: str | None, embed: Embedder | None = None
) -> int:
    from retrieval import sqlite_store

    path = sqlite_path or sqlite_store.SQLITE_PATH
    changed = 0
    conn = sqlite_store.connect(path)
    try:
        sqlite_store.create_schema(conn)
        for doc in documents:
            content_hash = compute_hash(doc["text"])
            row = conn.execute(
                "SELECT id, content_hash FROM documents WHERE url = ?", (doc["url"],)
            ).fetchone()
            if row and row[1] == content_hash:
                continue

            chunks, embeddings, refs_per_chunk = _prepare_chunks(doc["text"], embed)
            if not chunks:
                continue

            if row:
                doc_id = row[0]
                old_chunk_ids = [
                    r[0]
                    for r in conn.execute(
                        "SELECT id FROM chunks WHERE document_id = ?", (doc_id,)
                    ).fetchall()
                ]
                # No ON DELETE CASCADE on chunks.document_id here, and the fts5/
                # vec0 virtual tables aren't wired to chunks via triggers, so
                # every side needs an explicit delete before re-inserting.
                for chunk_id in old_chunk_ids:
                    conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (chunk_id,))
                    conn.execute("DELETE FROM chunks_vec WHERE rowid = ?", (chunk_id,))
                conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
                conn.execute(
                    "UPDATE documents SET title = ?, license = ?, published_at = ?, "
                    "content_hash = ? WHERE id = ?",
                    (
                        doc["title"],
                        doc.get("license"),
                        doc.get("published_at"),
                        content_hash,
                        doc_id,
                    ),
                )
            else:
                doc_id = sqlite_store.insert_document(
                    conn,
                    doc["source"],
                    doc["url"],
                    doc["title"],
                    doc.get("license"),
                    doc.get("published_at"),
                    content_hash,
                )

            sqlite_store.insert_chunks(conn, doc_id, chunks, embeddings, refs_per_chunk)
            conn.commit()
            changed += 1
    finally:
        conn.close()
    return changed
