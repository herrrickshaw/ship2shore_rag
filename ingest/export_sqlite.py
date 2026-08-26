"""Shore-side: snapshot the Postgres corpus into a single portable SQLite file
for vessel deployment. Run after ingesting, before syncing aboard."""

import os

import psycopg
from pgvector.psycopg import register_vector

from config import DATABASE_URL, SQLITE_PATH
from retrieval import sqlite_store


def export_sqlite(sqlite_path: str = SQLITE_PATH) -> tuple[int, int]:
    if os.path.exists(sqlite_path):
        os.remove(sqlite_path)

    with psycopg.connect(DATABASE_URL) as pg_conn:
        register_vector(pg_conn)
        documents = pg_conn.execute(
            "SELECT id, source, url, title, license, published_at FROM documents"
        ).fetchall()

        lite_conn = sqlite_store.connect(sqlite_path)
        sqlite_store.create_schema(lite_conn)

        doc_count = chunk_count = 0
        for pg_doc_id, source, url, title, license, published_at in documents:
            published_at_str = published_at.isoformat() if published_at else None
            new_doc_id = sqlite_store.insert_document(
                lite_conn, source, url, title, license, published_at_str
            )
            chunks = pg_conn.execute(
                "SELECT content, embedding, regulation_refs FROM chunks "
                "WHERE document_id = %s ORDER BY chunk_index",
                (pg_doc_id,),
            ).fetchall()
            if not chunks:
                continue
            contents = [c[0] for c in chunks]
            embeddings = [c[1].to_list() for c in chunks]
            regulation_refs = [c[2] for c in chunks]
            sqlite_store.insert_chunks(lite_conn, new_doc_id, contents, embeddings, regulation_refs)
            doc_count += 1
            chunk_count += len(contents)

        lite_conn.commit()
        lite_conn.close()

    return doc_count, chunk_count


if __name__ == "__main__":
    docs, chunks = export_sqlite()
    print(f"exported {docs} documents / {chunks} chunks to {SQLITE_PATH}")
