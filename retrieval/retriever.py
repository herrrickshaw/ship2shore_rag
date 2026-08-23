"""Embeds a query and cosine-searches top-k chunks in pgvector."""
import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector

from config import DATABASE_URL
from ingest.embed import embed_query


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    query_embedding = Vector(embed_query(query))
    with psycopg.connect(DATABASE_URL) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.content, d.title, d.url, d.source,
                       1 - (c.embedding <=> %s) AS similarity
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                ORDER BY c.embedding <=> %s
                LIMIT %s
                """,
                (query_embedding, query_embedding, top_k),
            )
            rows = cur.fetchall()
    return [
        {"content": r[0], "title": r[1], "url": r[2], "source": r[3], "similarity": float(r[4])}
        for r in rows
    ]
