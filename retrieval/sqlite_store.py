"""Single-file SQLite + sqlite-vec backend — no server, no network.

Built shore-side by `cli.py export-sqlite` from the Postgres corpus, then copied
aboard (USB / low-bandwidth sync). Retrieval here needs nothing but this one
file: no Postgres, no internet. Generation (Claude) is still optional and still
needs connectivity — see README "Shipboard deployment".
"""
import sqlite3

import sqlite_vec

from config import EMBEDDING_DIM, SQLITE_PATH

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    license TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content, content='chunks', content_rowid='id'
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
    embedding float[{EMBEDDING_DIM}]
);
"""


def connect(path: str = SQLITE_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def insert_document(conn: sqlite3.Connection, source: str, url: str, title: str, license: str | None) -> int:
    cur = conn.execute(
        "INSERT INTO documents (source, url, title, license) VALUES (?, ?, ?, ?)",
        (source, url, title, license),
    )
    return cur.lastrowid


def insert_chunks(conn: sqlite3.Connection, document_id: int, chunks: list[str], embeddings: list[list[float]]) -> None:
    for i, (content, embedding) in enumerate(zip(chunks, embeddings)):
        cur = conn.execute(
            "INSERT INTO chunks (document_id, chunk_index, content) VALUES (?, ?, ?)",
            (document_id, i, content),
        )
        chunk_id = cur.lastrowid
        conn.execute("INSERT INTO chunks_fts (rowid, content) VALUES (?, ?)", (chunk_id, content))
        conn.execute(
            "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
            (chunk_id, sqlite_vec.serialize_float32(embedding)),
        )


def retrieve(
    query: str,
    query_embedding: list[float],
    top_k: int = 5,
    fetch_k: int = 30,
    rrf_k: int = 60,
    path: str = SQLITE_PATH,
) -> list[dict]:
    """Hybrid retrieval: dense (vec0 cosine) + sparse (FTS5 BM25), fused via
    Reciprocal Rank Fusion — the pattern the Multi-Field Hybrid RAG paper (arXiv
    2606.13249) used for maritime accident-report retrieval."""
    conn = connect(path)
    try:
        dense_rows = conn.execute(
            """
            SELECT rowid, distance FROM chunks_vec
            WHERE embedding MATCH ? AND k = ?
            ORDER BY distance
            """,
            (sqlite_vec.serialize_float32(query_embedding), fetch_k),
        ).fetchall()
        dense_rank = {row[0]: i for i, row in enumerate(dense_rows)}

        sparse_rows = conn.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, fetch_k),
        ).fetchall()
        sparse_rank = {row[0]: i for i, row in enumerate(sparse_rows)}

        fused: dict[int, float] = {}
        for rowid, rank in dense_rank.items():
            fused[rowid] = fused.get(rowid, 0.0) + 1.0 / (rrf_k + rank)
        for rowid, rank in sparse_rank.items():
            fused[rowid] = fused.get(rowid, 0.0) + 1.0 / (rrf_k + rank)

        top_ids = sorted(fused, key=fused.get, reverse=True)[:top_k]
        if not top_ids:
            return []

        placeholders = ",".join("?" * len(top_ids))
        rows = conn.execute(
            f"""
            SELECT c.id, c.content, d.title, d.url, d.source
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.id IN ({placeholders})
            """,
            top_ids,
        ).fetchall()
        by_id = {r[0]: r for r in rows}
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
    finally:
        conn.close()
