"""One-time backfill: recompute regulation_refs for every existing chunk.

Needed because content_hash-based freshness tracking (by design) skips
re-processing unchanged text -- correct for the expensive part
(re-embedding), but it also means a brand-new derived-metadata feature
like regulation_refs never gets computed for chunks ingested before the
feature existed, since nothing about their content_hash changed. This
recomputes just the cheap, regex-only part (no re-fetch, no re-embed) for
every chunk already in the corpus, once."""

from config import STORAGE_BACKEND
from ingest.regulation_refs import extract_refs


def _backfill_postgres() -> int:
    import psycopg
    from psycopg.types.json import Json

    from config import DATABASE_URL

    updated = 0
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, content FROM chunks")
            rows = cur.fetchall()
        for chunk_id, content in rows:
            refs = extract_refs(content)
            if not refs:
                continue
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE chunks SET regulation_refs = %s WHERE id = %s", (Json(refs), chunk_id)
                )
            updated += 1
        conn.commit()
    return updated


def _backfill_sqlite(sqlite_path: str | None) -> int:
    import json

    from retrieval import sqlite_store

    path = sqlite_path or sqlite_store.SQLITE_PATH
    conn = sqlite_store.connect(path)
    try:
        rows = conn.execute("SELECT id, content FROM chunks").fetchall()
        updated = 0
        for chunk_id, content in rows:
            refs = extract_refs(content)
            if not refs:
                continue
            conn.execute(
                "UPDATE chunks SET regulation_refs = ? WHERE id = ?", (json.dumps(refs), chunk_id)
            )
            updated += 1
        conn.commit()
        return updated
    finally:
        conn.close()


def backfill(sqlite_path: str | None = None) -> int:
    """Returns the number of chunks whose regulation_refs was set to a
    non-empty value (chunks with no regulation language are left at the
    schema default '[]', not touched)."""
    if STORAGE_BACKEND == "sqlite":
        return _backfill_sqlite(sqlite_path)
    return _backfill_postgres()


if __name__ == "__main__":
    n = backfill()
    print(f"backfilled regulation_refs for {n} chunk(s)")
