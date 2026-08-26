# Changelog

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
