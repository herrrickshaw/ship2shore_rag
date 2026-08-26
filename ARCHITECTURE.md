# Architecture

This document structures ship2shore_rag through two lenses: **TOGAF's four
architecture domains** (what the system is, layer by layer) and the **Data
Analytics Lifecycle** (how the system was actually built, and how it keeps
improving). Both are standard frameworks, applied here to a real, specific
system rather than described in the abstract — every claim below names an
actual file, table, or measured number.

## TOGAF view: four architecture domains

### Business Architecture — what problem, for whom

Free, legally-open maritime/shipping literature (arXiv, Wikipedia, MAIB,
NTSB, IMO, UKHO NtM) made queryable with citations, for two distinct
consumers with different constraints:

- **Shore-side**: full corpus, live ingestion, optional generation —
  Postgres, always-connected.
- **Vessel-side**: a portable read-only snapshot, no server, no network —
  SQLite, built by `cli.py export-sqlite`. See README "Shipboard
  deployment" for why this split exists (VSAT/FleetBroadband bandwidth,
  not always-on internet).

A [market survey](https://claude.ai/code/artifact/7bfb100c-35be-4b5d-aa7f-4fc4c5a5476c)
found every well-funded competitor (DNV RuleAgent, Marcura, Veson
CoCaptain) gated behind proprietary/licensed data — the business case here
is specifically the gap they leave: free, self-hostable, legally-open-only.

### Data Architecture — what's stored, where

| Store | Contents | Backend |
|---|---|---|
| `documents` / `chunks` | literature corpus: source, url, title, license, `published_at`, `content_hash`, chunk text + embedding | Postgres/pgvector (shore) or SQLite/sqlite-vec (vessel, `retrieval/sqlite_store.py`) |
| `ops_*` tables | vessel/crew/logs/maintenance/procurement/drydock/safety | Postgres or SQLite, `ops/store.py` — a genuinely separate concern from the literature corpus, different write pattern (live operational data, not a read-mostly snapshot) |
| `query_log.jsonl` | one line per `ask()` call — question, passages, scores | flat file, gitignored, local-only |
| `ship_telemetry.duckdb` | simulated sensor/position data (warehouse/) | DuckDB, single embedded file — architecturally unrelated to the RAG corpus, kept separate |

`content_hash` (sha256 of fetched text) is the load-bearing piece of the
data model that isn't obvious from the schema alone: it's what lets
re-ingesting an already-seen URL distinguish "unchanged, skip" from
"changed, update in place" (`ingest/freshness.py`) instead of silently
duplicating or silently going stale.

### Application Architecture — the pipeline

```
ingest/sources.py, loaders.py  -> fetch (arxiv/wikipedia/maib/ntsb/ntm/pdf/html/file)
ingest/chunk.py, embed.py      -> chunk + embed locally
ingest/ingest.py               -> upsert, freshness-aware (postgres or sqlite)
        |
retrieval/retriever.py  -> RRF fusion (dense cosine + sparse keyword)
retrieval/rerank.py     -> cross-encoder rescoring of the candidate pool
retrieval/diversify.py  -> final top-k cut: per-source cap + dedup
        |
rag/pipeline.py    -> cited prompt, optional Claude generation
rag/cite_check.py  -> flags out-of-range / weakly-grounded citations
        |
cli.py (CLI) | webui/ (browser) | api.py (ops REST, separate auth model)
```

Every stage above is independently swappable because each does exactly one
job — this is what let reranking, diversity filtering, and metadata
filtering each land as an isolated change to `retriever.py`'s pipeline
this session without touching the stages around them.

### Technology Architecture — what it runs on

Local-first by deliberate choice at every layer, not just the obvious one:
`sentence-transformers` for embeddings (not an embedding API),
`cross-encoder/ms-marco-MiniLM-L-6-v2` for reranking (same reasoning),
Claude generation is optional (extractive fallback works with zero API
calls), Jina AI Reader is the one exception — an external service, used
only for public HTML pages in `sources.yaml`, explicitly not for anything
under restricted redistribution terms (`--source file` stays fully local
for those). FastAPI + uvicorn for both `api.py` and `webui/server.py`.
Docker/GHCR for the ops API; Fly.io deploy config exists but requires the
user's own account setup.

## Data Analytics Lifecycle: how this was actually built

The EMC/Pivotal *Data Science & Big Data Analytics* lifecycle (Discovery →
Data Preparation → Model Planning → Model Building → Communicate Results →
Operationalize) maps cleanly onto this project's real history — not as a
retrofit, but because building a retrieval pipeline genuinely is a data
analytics problem:

1. **Discovery** — the MECE competitive/literature survey that scoped this
   project before any code existed: what sources are legally free, what
   the market gap actually is.
2. **Data Preparation** — `ingest/`: fetch, chunk (`chunk.py`, 220-word
   windows/40-word overlap), embed, upsert with freshness tracking.
3. **Model Planning** — the retrieval *approach* decisions: hybrid
   dense+sparse over pure vector (RRF, matching the Multi-Field Hybrid RAG
   paper's pattern for this exact domain), reranking over trusting RRF's
   own cutoff, Recall@k/MRR over RAGAS (no LLM judge needed to measure
   whether the right passage got retrieved).
4. **Model Building** — the actual implementation: `retriever.py`,
   `rerank.py`, `diversify.py`, `cite_check.py`.
5. **Communicate Results** — `rag/pipeline.py`'s cited prompt, `rag/export.py`'s
   compact reports, `webui/` for browser access, `cli.py ask` for the CLI.
6. **Operationalize** — CI (`quality-gates.yml`), Docker/GHCR for the ops
   API, and critically: `eval/evaluate.py` — the mechanism that makes every
   later change to this pipeline measurable rather than a guess.

## Kaizen: the improvement loop, not just the pipeline

Operationalize isn't a one-time endpoint — `eval/evaluate.py` closes a
Plan-Do-Check-Act loop that already caught a real defect in this project's
own history: `retrieval/diversify.py`'s first version used
`difflib.SequenceMatcher.quick_ratio()` for near-duplicate detection
(**Plan**: dedup should improve results). Shipping it and re-running the
eval harness (**Do**) measured recall@5 dropping from 0.93 to 0.47 with
reranking off (**Check**) — `quick_ratio()` was flagging unrelated
boilerplate as duplicates. Switching to `.ratio()` and re-measuring
(**Act**) confirmed the fix restored baseline numbers. See
[CHANGELOG.md](CHANGELOG.md)'s "Redundancy / near-duplicate filtering"
entry for the full before/after — the point isn't that a bug happened, the
point is that the loop *caught it before it shipped* instead of after.

The same loop is why `CHANGELOG.md` records decisions and rejected
alternatives, not just diffs (Cassandra+Flink → DuckDB is the clearest
example: a whole architecture tried, measured against this project's
actual needs, and deliberately reverted) — a Kaizen log is only useful if
it's honest about what didn't work, not just what shipped.

## Where this document stops

This is a structural map, not a tutorial — see [README.md](README.md) for
setup/usage, [CHANGELOG.md](CHANGELOG.md) for the decision history, and
`PLAN.md`/`gates/` for the evidence trail behind the largest single batch
of changes (the orchestrated "close the remaining gaps" build).
