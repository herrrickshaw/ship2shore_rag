CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    source      TEXT NOT NULL,          -- 'arxiv' | 'wikipedia' | 'pdf' | ...
    url         TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    license     TEXT,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Nullable: only arxiv/maib fetchers actually have a real publish/report
-- date to extract (wikipedia/pdf/file don't). init_db.py re-executes this
-- whole script idempotently on every run, and Postgres 9.6+ supports
-- ADD COLUMN IF NOT EXISTS directly, so this needs no separate migration
-- mechanism.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS chunks (
    id           SERIAL PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  INTEGER NOT NULL,
    content      TEXT NOT NULL,
    embedding    vector(384) NOT NULL,
    content_tsv  tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Sparse (keyword) side of hybrid retrieval — fused with the dense index above
-- via Reciprocal Rank Fusion in retrieval/retriever.py.
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (content_tsv);
