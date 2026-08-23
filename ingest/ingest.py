"""Orchestrates fetch -> chunk -> embed -> upsert into pgvector."""
import psycopg
from pgvector.psycopg import register_vector

from config import DATABASE_URL
from ingest.chunk import chunk_text
from ingest.embed import embed_texts


def ingest_documents(documents: list[dict]) -> int:
    """Upserts documents + their chunks/embeddings. Returns count of documents ingested
    (documents already present by URL are skipped, not re-embedded)."""
    ingested = 0
    with psycopg.connect(DATABASE_URL, autocommit=False) as conn:
        register_vector(conn)
        for doc in documents:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM documents WHERE url = %s", (doc["url"],))
                if cur.fetchone():
                    continue

                chunks = chunk_text(doc["text"])
                if not chunks:
                    continue
                embeddings = embed_texts(chunks)

                cur.execute(
                    "INSERT INTO documents (source, url, title, license) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    (doc["source"], doc["url"], doc["title"], doc.get("license")),
                )
                doc_id = cur.fetchone()[0]

                cur.executemany(
                    "INSERT INTO chunks (document_id, chunk_index, content, embedding) "
                    "VALUES (%s, %s, %s, %s)",
                    [
                        (doc_id, i, chunk, embedding)
                        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
                    ],
                )
            conn.commit()
            ingested += 1
    return ingested
