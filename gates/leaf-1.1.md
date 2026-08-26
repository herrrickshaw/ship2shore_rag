# Gates: incremental re-crawl / freshness tracking

Scope: already-ingested documents whose source content has changed get
re-chunked/re-embedded on the next ingest run instead of being silently
skipped by URL, using a content hash to detect the change.

- [x] G1: documents.content_hash column exists on both backends
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && .venv/bin/python3 -c "import psycopg; from config import DATABASE_URL; c=psycopg.connect(DATABASE_URL); print(c.execute(\"SELECT column_name FROM information_schema.columns WHERE table_name='documents' AND column_name='content_hash'\").fetchone())"
  EXPECT: content_hash
  EVIDENCE: ran `.venv/bin/python3 -m db.init_db` to apply the new `ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash TEXT;` in db/schema.sql to the live Postgres instance (output: "schema ready at postgresql://localhost:5433/ship2shore"). CHECK command then returned `('content_hash',)`. sqlite side: retrieval/sqlite_store.py SCHEMA's documents table now includes `content_hash TEXT`, plus a try/except ALTER TABLE guard in create_schema() for pre-existing snapshot files, mirroring the published_at pattern exactly.

- [x] G2: ingest/freshness.py exists with a compute_hash(text) function
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && .venv/bin/python3 -c "from ingest.freshness import compute_hash; print(len(compute_hash('hello world')))"
  EXPECT: 64
  EVIDENCE: command output: `64`. ingest/freshness.py: `compute_hash(text)` returns `hashlib.sha256(text.encode("utf-8")).hexdigest()`.

- [x] G3: ingesting a brand-new document stores a non-null content_hash
  CHECK: (script provided in leaf brief — ingest a throwaway doc, query content_hash IS NOT NULL)
  EXPECT: pending
  EVIDENCE: verify script at /private/tmp/claude-501/-Users-umashankar/e34a6caa-4520-45e0-836f-109e4f79a4a2/scratchpad/verify_freshness.py, run against live Postgres: `[postgres] G3 count1=1 doc_id=137 hash_not_null=True n_chunks=2`. Also passed against sqlite (temp file): `[sqlite] G3 count1=1 doc_id=1 hash_not_null=True n_chunks=2`.

- [x] G4: re-ingesting the exact same URL+content a second time is still a no-op (0 new/updated documents, chunk count unchanged) — this must NOT regress the existing "skip if URL exists" behavior for genuinely unchanged content
  CHECK: (script provided in leaf brief)
  EXPECT: pending
  EVIDENCE: postgres: `[postgres] G4 count2=0 hash_unchanged=True n_chunks_unchanged=True`. sqlite: `[sqlite] G4 count2=0 hash_unchanged=True n_chunks_unchanged=True`. ingest_documents() returned 0 in both, hash and chunk count identical to the G3 run.

- [x] G5: re-ingesting the same URL with CHANGED text replaces the old chunks (old chunk content is gone, new chunk content is present, content_hash updated)
  CHECK: (script provided in leaf brief)
  EXPECT: pending
  EVIDENCE: postgres: `[postgres] G5 count3=1 doc_id_same=True hash_changed=True old_gone=True new_present=True n_chunks3=1`. sqlite: `[sqlite] G5 count3=1 doc_id_same=True hash_changed=True old_gone=True new_present=True n_chunks3=1`. Same document id retained (UPDATE not new INSERT), VERSION_ONE_MARKER chunk text gone, VERSION_TWO_MARKER chunk text present, content_hash differs from the G3 hash.

- [x] G6: works for both STORAGE_BACKEND=postgres (live, against the real running instance on 5433) and STORAGE_BACKEND=sqlite (a temp file)
  CHECK: (script provided in leaf brief, run once per backend)
  EXPECT: pending
  EVIDENCE: full verify_freshness.py (G3+G4+G5 in sequence) run twice: `STORAGE_BACKEND=postgres ... -> [postgres] ALL OK` (exit 0) against the live 5433 instance, and `STORAGE_BACKEND=sqlite SQLITE_PATH=/tmp/leaf11_XXXX.sqlite3 ... -> [sqlite] ALL OK` (exit 0) against a throwaway temp file. Post-run cleanup verified on Postgres: `leftover test doc (0,)`, `orphan chunks (0,)` — the throwaway doc was fully removed, live 131-doc corpus left intact (only unrelated concurrent-leaf activity changed the total count, not this test).

- [x] G7: tests/test_freshness.py exists and passes standalone
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && .venv/bin/python3 -m pytest -q tests/test_freshness.py
  EXPECT: passed
  EVIDENCE: `.....  [100%]  5 passed in 0.32s`. Covers: compute_hash is 64-char hex + deterministic; new doc gets non-null content_hash; unchanged re-ingest is a no-op (count 0, hash/chunks unchanged); changed re-ingest updates the same doc row in place (old chunk text gone, new chunk text present, hash changed); whitespace-only text is skipped without error. Runs against sqlite backend via a tempfile (monkeypatches ingest.ingest.STORAGE_BACKEND + embed_texts, no live Postgres or real model load needed) — standalone and CI-safe, same pattern as tests/test_sqlite_store.py.

- [x] G8: full existing CI-whitelisted test suite still passes (no regression)
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && .venv/bin/python3 -m pytest -q tests/test_chunk.py tests/test_sources.py tests/test_sqlite_store.py tests/test_loaders.py tests/test_export.py tests/test_ops_auth.py tests/test_ops_store.py tests/test_api.py
  EXPECT: passed
  EVIDENCE: `..............................................  [100%]  46 passed, 1 warning in 0.77s`. Warning is a pre-existing unrelated httpx/starlette deprecation notice in test_api.py, not caused by this leaf's changes.

<!--
Leaf brief context: db/schema.sql already has ALTER TABLE ... ADD COLUMN
IF NOT EXISTS published_at TIMESTAMPTZ as a precedent for this exact kind
of idempotent migration (Postgres 9.6+ supports IF NOT EXISTS on ADD
COLUMN, no separate migration mechanism needed since init_db.py
re-executes the whole schema every run). retrieval/sqlite_store.py's
create_schema() has the equivalent try/except sqlite3.OperationalError
pattern for the SQLite side (no IF NOT EXISTS there). Follow both patterns
exactly for content_hash. ingest/ingest.py's current logic: SELECT id FROM
documents WHERE url = %s; if found, `continue` (skip entirely, never
re-chunks). Change this to: if found, compare content_hash; if unchanged,
continue (current behavior preserved); if changed, DELETE the old chunks
(document_id, cascades or explicit DELETE FROM chunks WHERE document_id=%s
first if no ON DELETE CASCADE convenience applies here — check chunks'
FK), then UPDATE documents SET title=,license=,published_at=,content_hash=
WHERE id=%s, then proceed with the normal chunk/embed/insert path using the
existing document_id instead of inserting a new document row.
-->
