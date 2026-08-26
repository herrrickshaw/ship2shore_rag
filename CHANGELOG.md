# Changelog

## [Unreleased] — 2026-08-26 — ARCHITECTURE.md

### Added
- **`ARCHITECTURE.md`** — a structural map of the system through two
  standard frameworks applied to this actual codebase (not described in
  the abstract): TOGAF's four architecture domains (Business/Data/
  Application/Technology) and the EMC/Pivotal Data Analytics Lifecycle
  (Discovery → Data Preparation → Model Planning → Model Building →
  Communicate Results → Operationalize), plus a Kaizen/PDCA framing of the
  eval-harness-driven improvement loop, citing this session's own
  diversify.py `quick_ratio()` bug (caught and fixed via that exact loop)
  as the concrete example rather than a hypothetical one. Two of the four
  source documents the user pointed to were blocked by the same Google
  Drive CloudStorage permission issue from earlier this session (`EPERM`)
  — only the readable one's real table of contents (the Data Analytics
  Lifecycle chapter) was used verbatim; SDLC/TOGAF content is applied from
  general knowledge of those standard frameworks, not from the
  inaccessible source PDFs.

## [Unreleased] — 2026-08-26 — 9 more IMO convention pages via type: html

### Added
- **9 IMO convention pages** (SOLAS, MARPOL, STCW, Load Lines, ISM Code,
  ISPS Code, Ballast Water Management, Tonnage Measurement, Search and
  Rescue) added to `ingest/sources.yaml` as `type: html` entries — primary-
  source IMO content, distinct from (and more authoritative than) the
  Wikipedia summaries already covering some of the same conventions.
  Verified each page's actual content before adding, not just its HTTP
  status: COLREGs' own IMO page returns a genuine 500 under a 200-wrapped
  "Coming Soon" stub (confirmed live), so it's documented and skipped
  rather than ingesting a broken page. Verified live end-to-end through
  `cli.py ingest`: 9/9 landed with real content (55 chunks total,
  3–11 chunks each), and a retrieval spot-check confirmed the new content
  is genuinely retrievable and ranks sensibly alongside the existing
  Wikipedia coverage rather than either crowding it out or sitting unused.
  Corpus: 577 → 587 documents.

## [Unreleased] — 2026-08-26 — HTML sources in sources.yaml via Jina Reader

### Added
- **`type: html` entries in `ingest/sources.yaml`** — non-PDF public web
  pages (port authority pages, IMO circulars, industry white papers) are
  now genuinely supported, not just documented-but-broken (they'd have
  silently mis-processed as PDFs before this). Fetched as clean markdown
  via [Jina AI Reader](https://r.jina.ai/) (`fetch_url_via_reader()` in
  `ingest/sources.py`, free tier, no API key) instead of raw HTML scraping,
  rather than adding a heavier local dependency (e.g. Crawl4AI's
  Playwright/Chromium requirement) for a repo that's stayed deliberately
  light everywhere else — chosen specifically because nothing currently
  ingested needs real JS rendering. Publish dates in Reader's response are
  validated against the same strict ISO-8601 parse `retriever.py`'s
  `_passage_date()` uses before being stored, rather than trusted as-is —
  a malformed date from some page's metadata must be dropped at fetch
  time, not surface as a crash in `ask --since ...` later.
  Third-party-proxy caveat stated explicitly in both the code and
  `sources.yaml`'s header comment: fine for public pages, not appropriate
  for anything under restricted redistribution terms (use `--source file`
  for those). Verified live end-to-end through `cli.py ingest`, not just
  the fetcher in isolation: added the Maritime Labour Convention (a real,
  previously-missing maritime-regulation topic) as the first `type: html`
  entry — landed with 28 chunks, correct title/license, and a real
  `published_at` extracted from the page's own metadata.

## [Unreleased] — 2026-08-26 — Close the remaining "Not yet done" gaps

Orchestrated build (per the `unlazy` skill's Depth Tree method, gates-and-
evidence discipline — `ruflo`'s swarm/agent-spawn tooling was configured but
unreachable, `claude mcp list` timing out on both `ruflo` and its
`claude-flow` alias, so the Agent tool substituted as the actual per-leaf
fresh-context dispatch mechanism). Four independent, file-disjoint leaves,
each formally re-verified by re-running its gates myself rather than
trusting its self-report (per the skill's stated verification hierarchy).
`PLAN.md`/`gates/` in the repo root have the full contract and evidence
trail if you want the details behind any of these.

### Added
- **Incremental re-crawl / freshness tracking.** `documents.content_hash`
  (sha256 of the fetched text) lets re-ingesting an already-seen URL tell
  "unchanged" (skip, previous behavior) apart from "changed" (re-chunk/
  re-embed in place instead of silent skip or duplicate) — `ingest/
  freshness.py`, `ingest/ingest.py` rewritten to dispatch on
  `STORAGE_BACKEND` like `retrieval/retriever.py` already does. Verified
  live against both backends: ingest, mutate, re-ingest — chunks replaced
  correctly, document id stable.
- **Chunk-level citation verification.** `rag/cite_check.py` checks a
  generated answer's `[n]` markers against the passages actually retrieved:
  flags out-of-range citations (hallucinated numbering) and weakly-grounded
  ones (a real passage number whose content doesn't actually support the
  citing sentence — word-set Jaccard overlap, no LLM call). Run against a
  real query on the live corpus during verification, it correctly caught
  both an out-of-range citation and a sentence that actually contradicted
  its cited passage's real content, not just loosely paraphrased it.
- **Automated NTSB crawler.** The README's prior claim — "CAROL's API isn't
  public/documented" — turned out to be wrong when actually investigated
  live: `data.ntsb.gov/carol-main-public`'s search grid is backed by a
  plain, unauthenticated JSON endpoint, reverse-engineered from the app's
  own unminified client JS and confirmed by replicating the whole flow from
  a bare Python `requests.Session()` outside the browser. `fetch_ntsb()`
  (`ingest/sources.py`, additive-only) discovers ~450 real marine reports
  this way vs. the 3 that were hand-curated before — `cli.py ingest
  --source ntsb`.
- **Minimal web UI.** `cli.py serve` — a small dedicated FastAPI app
  (`webui/`, separate from `api.py`'s ops REST API: read-only, no
  credentials) serving one self-contained HTML page. Localhost-only by
  default (`WEBUI_HOST` to opt into anything else). Works against both
  storage backends.

## [Unreleased] — 2026-08-26 — Lint tooling, test coverage, SQLite FTS5 crash fix

### Added
- **ruff + black**, matching the exact convention already used across this
  account's other repos (`global-market-data`, `global-stock-screener`):
  line-length 100, `[tool.ruff]`/`[tool.black]` in `pyproject.toml`,
  `.pre-commit-config.yaml` with the same hook versions. `requirements-
  dev.txt` for the scoped dev-only deps (ruff, black, pre-commit,
  pytest-cov), matching the `requirements-api.txt`/`requirements-
  warehouse.txt` scoped-file pattern. Ran across the whole tree: one
  real issue found (an unsorted import block in `cli.py`), fixed; every
  other file was already clean.
- **Unit tests for the retrieval pipeline built this session** — it had
  zero test coverage (only manually/live-verified) despite being the
  bulk of today's work: `tests/test_diversify.py` (redundancy filtering),
  `tests/test_query_log.py`, `tests/test_retriever_filters.py`
  (`since`/`source_filter` post-filtering). Coverage run
  (`pytest --cov`) is what surfaced this gap concretely rather than by
  guess.

### Fixed
- **SQLite backend crashed on any normal question.** `retrieval/
  sqlite_store.py`'s FTS5 keyword search passed the raw query string
  straight into `MATCH`, which treats it as FTS5 query syntax, not plain
  text (unlike Postgres's `plainto_tsquery()` on the other backend) — a
  bare `?` (or `"`, `*`, `-`, ...) is a syntax error, not a literal
  character. Any question ending in `?` — i.e. almost any real question —
  crashed retrieval outright on the vessel-side/offline backend. Found by
  the leaf building the web UI (see below), confirmed by independent
  reproduction, fixed with a `_fts5_query()` helper that tokenizes and
  double-quotes each word (AND-joined, matching `plainto_tsquery`'s
  AND-every-lexeme semantics) — a quoted FTS5 term is always literal.
  Regression test added (`test_retrieve_does_not_crash_on_fts5_special_
  characters`, parametrized over `?`/`"`/`*`/`-`/empty-string).

## [Unreleased] — 2026-08-26 — Document metadata + query-time filtering

### Added
- **`documents.published_at`** (nullable) — Postgres via `ALTER TABLE
  documents ADD COLUMN IF NOT EXISTS` in `db/schema.sql` (no separate
  migration mechanism needed, `init_db.py` already re-executes the schema
  idempotently); SQLite via a `try/except sqlite3.OperationalError`-guarded
  `ALTER TABLE` in `sqlite_store.create_schema()` (SQLite has no `ADD
  COLUMN IF NOT EXISTS`).
- **`fetch_arxiv`/`fetch_maib`** (`ingest/sources.py`) now extract the Atom
  feed's `<published>`/`<updated>` date — both feeds already carried it,
  unused until now. `wikipedia`/`pdf`/`file` have no real publish-date
  source and stay `None`.
- **`retriever.retrieve(..., since=, source_filter=)`** — post-filters the
  candidate pool by publish date / ingestion source before reranking/
  diversify. First version, documented limitation: an aggressive filter can
  shrink the pool below `top_k` since RRF/`fetch_k` don't know about it yet
  (verified live: `--since 2026-01-01` on a query whose only 2026-dated
  match wasn't in that query's RRF pool correctly returned zero results
  rather than silently substituting something older).
- **`cli.py ask --since YYYY-MM-DD` / `--source-filter`** — CLI exposure,
  mirroring the existing `--no-generate`/`--no-rerank` flag pattern.

Phase 5 (final phase) of the measurable-retrieval plan. Verified live
end-to-end: `cli.py init-db` applied the migration to the running Postgres
instance; ingesting a new arXiv paper populated `published_at`
(`2026-05-13T10:30:07+05:30`); `cli.py export-sqlite` carried it through to
the SQLite snapshot (131 documents / 1,884 chunks); `--source-filter
wikipedia` and `--since` both filtered correctly. Eval harness confirmed no
regression (recall@5=0.93 / MRR unchanged both rerank settings).

## [Unreleased] — 2026-08-26 — Context-budget guard

### Added
- **`config.MAX_CONTEXT_CHARS`** (default 80,000, char count not tokens —
  no tokenizer dependency exists in this repo, not worth adding just for
  this) — `rag/pipeline.py:_build_context()` now stops adding passages once
  the budget is reached instead of concatenating every `top_k` passage
  unconditionally, printing how many were dropped. Not binding at today's
  `top_k=5`; guards against a future larger `top_k` silently overflowing the
  model's context window. Always keeps at least one passage even if it
  alone exceeds the budget, rather than returning empty context.

## [Unreleased] — 2026-08-26 — Redundancy / near-duplicate filtering

### Added
- **`retrieval/diversify.py`** — the final top_k cut, applied after
  reranking (or after RRF if reranking is off): caps results per source
  document (`max_per_source=2`) and skips near-duplicate passages via
  `difflib.SequenceMatcher.ratio()`. Fixes a redundancy problem the query
  log caught in the wild — a 3-result query had returned 3 chunks from the
  same NTSB report.
- `retrieval/rerank.py:rerank()` no longer cuts to `top_k` itself — it now
  scores and sorts the full candidate pool, leaving the cut to
  `diversify.select()` so dedup can skip candidates while walking the
  ranking instead of losing them to an earlier cut.

### Fixed (caught by Phase 2's own eval harness before this shipped)
- First version used `SequenceMatcher.quick_ratio()` for the near-duplicate
  check, which is a character-multiset upper bound, not real sequence
  similarity — on natural-language English text of similar length it runs
  high for almost any two paragraphs (similar letter frequency), not just
  genuinely duplicate ones. Running `cli.py eval` with reranking off caught
  this immediately: recall@5 dropped from 0.93 to 0.47 because the dedup
  pass was discarding correct passages, mistaking generic boilerplate
  letter-frequency overlap (UK government report front-matter, near-
  identical across every MAIB report) for real duplication. Switched to
  `.ratio()` (actual longest-matching-block comparison) — recall/MRR
  returned to baseline (0.93 / 0.633 rerank-off, 0.93 / 0.933 rerank-on)
  while the original redundancy fix (same-document cap) still holds.

## [Unreleased] — 2026-08-26 — Retrieval eval harness (Recall@k / MRR)

### Added
- **`eval/queries.yaml`** — 15 hand-curated queries against the real
  ingested corpus (one unambiguous expected URL each), spanning all 6
  ingestion sources (arxiv, wikipedia, maib, ntm, pdf, file).
- **`eval/evaluate.py`** — computes Recall@k and MRR for a query set, run
  with reranking on and off. Wired into `cli.py eval`. Not RAGAS — no LLM
  judge, runs offline, measures retrieval directly rather than generation
  quality.

Phase 2 of the measurable-retrieval plan (Phase 1: query logging). First
real numbers from it, run against the corpus (130 documents after this
session's ingestion): reranking took MRR from **0.633 to 0.933** at
identical recall@5 (0.93) — every hit that reranking found moved to rank 1
instead of being scattered across rank 1/2, which is exactly the effect a
cross-encoder rescoring pass should have. One genuine miss in both runs
("an open-source maritime industry-specific large language model" — the
Llamarine paper isn't surfacing in the top 5 either way) — a real finding
from the harness, not a bug, left as-is rather than chased down.

## [Unreleased] — 2026-08-26 — Query/retrieval logging

### Added
- **`retrieval/query_log.py`** — appends one JSON line per `ask()` call
  (question, top_k, rerank flag, retrieved passages with both RRF and
  rerank scores, whether generation ran) to `query_log.jsonl` (gitignored).
  Nothing logged a query before this. Phase 1 of a plan to make retrieval
  quality measurable rather than vibes-based: this is what the eval query
  set (next) gets seeded from. A logging failure can't break an answer —
  wrapped in `try/except OSError`.

## [Unreleased] — 2026-08-26 — Cross-encoder reranking

### Added
- **`retrieval/rerank.py`** — reranks the RRF-fused candidate pool with a
  local cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`, configurable
  via `RERANKER_MODEL`) before cutting to `top_k`. RRF only knows where each
  side (dense/sparse) ranked a chunk, never how relevant it actually is to
  the query — a cross-encoder scoring (query, passage) pairs directly is
  usually the biggest single relevance gain available in a hybrid retrieval
  pipeline, and it needed no new dependency (`sentence-transformers` was
  already pulled in for embeddings; `CrossEncoder` is the same package).
  `retriever.retrieve()` now pulls a wider `candidate_k` pool from RRF
  (default 20, was previously == `top_k`) so the cross-encoder has more than
  `top_k` candidates to actually choose among. Verified live against the
  real corpus: reranking visibly reordered results for "what causes engine
  room fires on cargo ships" — a bridge-allision report RRF ranked mid-pack
  correctly dropped to last, since it isn't actually about engine fires.
  `ask --no-rerank` / `retrieve(..., rerank=False)` falls back to RRF order.

## [Unreleased] — 2026-08-26 — Telemetry warehouse: Cassandra+Flink -> DuckDB

### Changed
- **`warehouse/`** — replaced the Cassandra + Flink stack with DuckDB for the
  ship telemetry data lake/warehouse.

### Removed
- **Flink** (`flink_job.py`, `Dockerfile.flink`, `jars/`) and **Cassandra**
  (`cassandra_schema.cql`, `cassandra_writer.py`) — Flink's official
  Cassandra connector (`flink-connector-cassandra_2.12`) turned out to have
  no Table API/SQL factory (verified directly: no
  `org.apache.flink.table.factories.Factory` entry in the JAR's
  `META-INF/services/`), so the natural `CREATE TABLE ... WITH ('connector'
  = 'cassandra', ...)` sink used throughout the original design doesn't
  exist to use. Working around that (DataStream API + a hand-written Python
  sink) added real complexity on top of memory tuning already fought once —
  Cassandra OOMing under 1024m heap, Flink refusing to start under ~768m
  process size — for a demo-scale, single-vessel-simulator telemetry feed
  that didn't need a clustered database in the first place.

### Added
- **`warehouse/schema.sql` + `warehouse/duckdb_writer.py`** — a single
  embedded DuckDB file (`ship_telemetry.duckdb`, gitignored) written
  directly by a plain Kafka consumer. The 1-minute windowed aggregation that
  Flink used to compute is now a SQL view (`time_bucket` + `GROUP BY`) over
  the raw table, recomputed at query time — no standing stream-processing
  job. This matches how every other repo in this account that accumulates
  readings over time and queries them handles it (`global-market-data`,
  `global-stock-screener`, `agri-commodity-tracker`,
  `market-correlation-matrices` all use a plain embedded file — DuckDB or
  Parquet — instead of a clustered database).
- **`requirements-warehouse.txt`** — scoped deps (`kafka-python`,
  `duckdb`) for the warehouse scripts, mirroring the existing
  `requirements-api.txt` pattern.

Kafka stays (KRaft mode, single container) — it's still doing real work
(decoupling the simulated producer from the consumer, replay-from-offset),
just no longer feeding a JVM cluster on the other end. Verified live:
producer -> Kafka -> `duckdb_writer.py`, 125 messages in, 100
`sensor_readings` + 25 `position_reports` out (exact match), aggregate view
correct (`sample_count=5` per vessel/sensor across 5 ticks).
