# Maritime shipping RAG (ship2shore_rag)

A retrieval-augmented generation (RAG) system for maritime and ocean-freight shipping knowledge:
vessel operations, port logistics, maritime regulation, and casualty/accident analysis. It ingests
literature from free, legal public sources (arXiv, Wikipedia, UK MAIB, US NTSB, UKHO Notices to
Mariners, plus any PDF or local file you add), embeds it locally, stores it in Postgres/pgvector, and
answers questions via hybrid dense + keyword retrieval with an optional cited answer from Claude.
Outputs are ranked passages, cited answers, compact HTML/text/Markdown reports, and a portable SQLite
snapshot for offline vessel-side use. A small operations module (crew, vessels, logs, maintenance) sits
alongside it.

> Status: active. Ingestion, hybrid retrieval and the vessel-side offline path work end to end;
> generation is optional and needs an Anthropic API key. Every ingestion source is one with a stated
> licence (see [Data sources](#data-sources)). Not for navigational or safety-critical decisions.

New to the repo? See [How to use this repo with AI](HOW_TO_USE_WITH_AI.md).

## What it does
- Ingests arXiv, Wikipedia, MAIB, NTSB, Notices to Mariners, PDF URLs and local PDF/TXT/MD/HTML/DOCX/XLSX/PPTX files.
- Hybrid retrieval (dense cosine + keyword) fused with Reciprocal Rank Fusion, then cross-encoder rerank and diversity filtering.
- Optional cited answers or ordered checklists from Claude; without an API key it returns the ranked passages.
- Citation grounding check and per-chunk IMO/CFR regulation-reference extraction.
- Offline vessel deployment from a single SQLite file (`export-sqlite`, `STORAGE_BACKEND=sqlite`).
- Retrieval eval harness (Recall@k / MRR), read-only web UI, ingestion microservice, and an operations REST API.

## Quick start
```bash
git clone https://github.com/herrrickshaw/ship2shore_rag.git
cd ship2shore_rag
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # DATABASE_URL points at localhost:5433/ship2shore
python3 cli.py init-db          # needs Postgres + pgvector running, see docs/setup-and-usage.md
python3 cli.py ingest --source arxiv
python3 cli.py ask "What causes hull fatigue cracking?" --no-generate
```
Full Postgres/pgvector setup and every CLI command: [docs/setup-and-usage.md](docs/setup-and-usage.md).

## How it works
```
ingest/sources.py, loaders.py -> fetch / load raw documents
ingest/chunk.py               -> overlapping word-window chunks
ingest/embed.py               -> local embeddings (sentence-transformers all-MiniLM-L6-v2)
ingest/ingest.py              -> upsert into Postgres/pgvector or SQLite/sqlite-vec (content-hash skip)
retrieval/retriever.py        -> dense + keyword search, fused by retrieval/fusion.py (RRF)
retrieval/rerank.py           -> cross-encoder rescoring of the candidate pool
retrieval/diversify.py        -> final top-k: per-source cap, near-duplicate skip
rag/pipeline.py               -> cited prompt to Claude (optional) or extractive passages
```
Design decisions: the embedder, reranker, storage backend and LLM are injectable (optional
`embed=`, `reranker=`, `backend=`, `generator=`, `retriever=` parameters) so tests run on fakes with no
database, model download or API key. Defaults are unchanged. RRF follows the Multi-Field Hybrid RAG
paper for maritime accident reports (arXiv 2606.13249). More detail: [docs/how-it-works.md](docs/how-it-works.md).

Stack: Postgres + pgvector (shore side), SQLite + sqlite-vec (vessel side), local sentence-transformers
embeddings (no key), Claude for optional generation (extractive mode is the only mode offline).

## Repository layout
| Path | Purpose |
|---|---|
| `cli.py`, `ops_cli.py` | Entry points: `init-db`, `ingest`, `ask`, `hazard-brief`, `training-gaps`, `export-sqlite`, `eval`, `serve`, `serve-ingest`, operations commands |
| `config.py` | Environment-driven settings (loads `.env`) |
| `ingest/` | Fetch, load, chunk, embed, freshness, regulation refs, registry, SQLite export |
| `retrieval/` | Hybrid retrieval, fusion, rerank, diversify, SQLite store, query log |
| `rag/` | Pipeline, citation check, export, hazard brief, similar incidents, training gaps |
| `ops/`, `api.py` | Operations store (SQLite) and its REST API |
| `webui/`, `ingest_service/` | Read-only web UI; ingestion microservice |
| `warehouse/` | Optional telemetry producer and DuckDB writer |
| `eval/` | Retrieval eval harness and `queries.yaml` |
| `db/` | Postgres schema and `init_db` |
| `snapshots/` | Latest vessel-side SQLite snapshot |
| `tests/` | pytest suite (fakes for DB, embedder, LLM) |
| `docs/` | Detailed guides moved out of the README |

## Data sources
| Source | What is taken | Access route | Licence / caveat |
|---|---|---|---|
| `arxiv` | Seed or custom search results | arXiv API | arXiv non-exclusive licence |
| `wikipedia` | Curated maritime articles | MediaWiki API | CC BY-SA 4.0 |
| `maib` | UK MAIB reports | `gov.uk/maib-reports.atom` | Open Government Licence v3.0 |
| `ntm` | UKHO weekly Notices to Mariners booklet | UKHO download | Free for navigational use; verify before redistribution |
| `ntsb` | US NTSB marine accident reports | CAROL search endpoint | US government work, public domain |
| `pdf` / `file` | Entries in `ingest/sources.yaml` / your own files | URL / local path | Varies; verify per entry |

Details and how to add sources: [docs/sources.md](docs/sources.md).

## Configuration
Set in `.env` (copy `.env.example`); no secret is committed.

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql://localhost/ship2shore` | Postgres connection |
| `STORAGE_BACKEND` | `postgres` | `sqlite` for vessel-side snapshot use |
| `SQLITE_PATH` | `ship2shore.sqlite3` | Snapshot file |
| `EMBEDDING_MODEL` / `RERANKER_MODEL` | `all-MiniLM-L6-v2` / `cross-encoder/ms-marco-MiniLM-L-6-v2` | Local models |
| `MAX_CONTEXT_CHARS` | `80000` | Context budget for generation |
| `ANTHROPIC_API_KEY` | empty | Optional; enables generated answers |
| `WEBUI_HOST`/`WEBUI_PORT`, `INGEST_SERVICE_HOST`/`INGEST_SERVICE_PORT` | `127.0.0.1`, `8020` / `8030` | Keep on localhost; these apps are unauthenticated |

## Testing
```bash
pip install -r requirements-dev.txt pytest
pytest -q
```
No live Postgres, model download or API key is needed.

## Documentation
[Setup and usage](docs/setup-and-usage.md) | [How it works](docs/how-it-works.md) | [Sources](docs/sources.md) |
[Shipboard deployment](docs/shipboard-deployment.md) | [Operations module and REST API](docs/operations-module.md) |
[Web UI and ingestion service](docs/web-ui-and-ingestion-service.md) | [Regulation references](docs/regulation-references.md) |
[ARCHITECTURE.md](ARCHITECTURE.md) | [GATES.md](GATES.md) | [CHANGELOG.md](CHANGELOG.md)

## Limitations and known issues
- `--export` writes a report file — it does not send email itself. Attach or
  paste it into your mail client of choice.
- Retrieval is not a predictive risk score; `hazard-brief` is retrieval only.
- The regulation-reference extraction is text extraction, not a temporal knowledge graph of superseded rules.

## Licence
No licence file yet: all rights reserved. Ingested documents keep their own licences (see Data sources).
