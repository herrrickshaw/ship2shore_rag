"""Single-file SQLite + sqlite-vec backend — no server, no network.

Built shore-side by `cli.py export-sqlite` from the Postgres corpus, then copied
aboard (USB / low-bandwidth sync). Retrieval here needs nothing but this one
file: no Postgres, no internet. Generation (Claude) is still optional and still
needs connectivity — see README "Shipboard deployment".
"""

import json
import re
import sqlite3

import sqlite_vec

from config import EMBEDDING_DIM, SQLITE_PATH

_WORD_RE = re.compile(r"\w+")


def _fts5_query(text: str) -> str:
    """FTS5's MATCH treats the raw string as query syntax, not plain text --
    unlike Postgres's plainto_tsquery() on the other backend, a bare "?" (or
    any of FTS5's other operator characters) is a syntax error, not a
    literal char to search for, so a completely normal question crashes
    retrieval outright. Tokenizing and double-quoting each word neutralizes
    that (a quoted FTS5 term is always literal) while keeping
    plainto_tsquery's AND-every-lexeme behavior, the closest sqlite-side
    equivalent."""
    return " AND ".join(f'"{w}"' for w in _WORD_RE.findall(text))


SCHEMA = f"""
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    license TEXT,
    published_at TEXT,
    content_hash TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    regulation_refs TEXT NOT NULL DEFAULT '[]'
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
    try:
        # SQLite has no ADD COLUMN IF NOT EXISTS. export_sqlite() always
        # deletes and rebuilds SQLITE_PATH fresh, so this only matters for
        # an older snapshot file (e.g. one already committed to the repo)
        # reused directly rather than re-exported.
        conn.execute("ALTER TABLE documents ADD COLUMN published_at TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    try:
        conn.execute("ALTER TABLE documents ADD COLUMN content_hash TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    try:
        conn.execute("ALTER TABLE chunks ADD COLUMN regulation_refs TEXT NOT NULL DEFAULT '[]'")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()


def insert_document(
    conn: sqlite3.Connection,
    source: str,
    url: str,
    title: str,
    license: str | None,
    published_at: str | None = None,
    content_hash: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO documents (source, url, title, license, published_at, content_hash) VALUES (?, ?, ?, ?, ?, ?)",
        (source, url, title, license, published_at, content_hash),
    )
    return cur.lastrowid


def insert_chunks(
    conn: sqlite3.Connection,
    document_id: int,
    chunks: list[str],
    embeddings: list[list[float]],
    regulation_refs: list[list[dict]] | None = None,
) -> None:
    refs_per_chunk = regulation_refs or [[] for _ in chunks]
    for i, (content, embedding, refs) in enumerate(zip(chunks, embeddings, refs_per_chunk)):
        cur = conn.execute(
            "INSERT INTO chunks (document_id, chunk_index, content, regulation_refs) VALUES (?, ?, ?, ?)",
            (document_id, i, content, json.dumps(refs)),
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

        fts_query = _fts5_query(query)
        sparse_rows = (
            conn.execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
                (fts_query, fetch_k),
            ).fetchall()
            if fts_query
            else []
        )
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
            SELECT c.id, c.content, d.title, d.url, d.source, d.published_at, c.regulation_refs
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
                "published_at": by_id[i][5],
                "regulation_refs": json.loads(by_id[i][6]),
                "score": fused[i],
            }
            for i in top_ids
            if i in by_id
        ]
    finally:
        conn.close()
