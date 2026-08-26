# ship2shore_rag

A retrieval-augmented generation (RAG) system for maritime/ocean-freight shipping
knowledge — vessel operations, port logistics, bills of lading, freight economics,
maritime regulation, and casualty/accident analysis. It ingests literature from
free, legal public sources (arXiv papers, Wikipedia, UK MAIB casualty reports, US
NTSB marine accident reports, and any PDF/URL you add), embeds it locally, stores
it in Postgres/pgvector, and answers questions via hybrid (dense + keyword)
retrieval with an optional cited answer from Claude.

A [market and literature survey](https://claude.ai/code/artifact/7bfb100c-35be-4b5d-aa7f-4fc4c5a5476c)
of the maritime-AI space shaped this scope: every well-funded competitor (DNV
RuleAgent, Marcura, Veson CoCaptain, MarineGPT.in) is grounded in proprietary,
licensed, or paywalled data behind a login. Nothing found offers a free,
self-hostable RAG over only legally-open literature — that's the gap this project
sits in, and it's why every ingestion source here is one you can point to and say
"I have the right to use this."

**Status:** ingestion, hybrid retrieval, and a vessel-side offline deployment path
all work end-to-end; generation is optional and requires an Anthropic API key.

## Stack

- **Postgres + [pgvector](https://github.com/pgvector/pgvector)** — shore-side chunk
  storage and hybrid retrieval (dense cosine + Postgres full-text search, fused via
  Reciprocal Rank Fusion).
- **SQLite + [sqlite-vec](https://github.com/asg017/sqlite-vec)** — vessel-side: the
  same hybrid retrieval (dense + FTS5 BM25) against a single portable file, no
  server, no network. See **Shipboard deployment** below.
- **sentence-transformers (`all-MiniLM-L6-v2`)** — local, free, no API key needed for
  embeddings, and small/CPU-only enough to run on modest hardware.
- **Claude (optional)** — generates a cited answer from retrieved passages. Without
  `ANTHROPIC_API_KEY` set, `ask` falls back to returning the raw ranked passages
  (extractive mode, still fully functional, and the only mode available offline).

## Setup

```bash
# 1. Postgres + pgvector (macOS/Homebrew)
# pgvector's bottle only ships builds for the latest 1-2 Postgres majors, so if
# you're on an older `postgresql@N` this may not have a build for it — that's
# why this project runs its own isolated instance on port 5433 rather than
# reusing whatever Postgres you already have.
brew install postgresql@17 pgvector
LC_ALL="en_US.UTF-8" /opt/homebrew/opt/postgresql@17/bin/pg_ctl \
  -D /opt/homebrew/var/postgresql@17 -l /opt/homebrew/var/postgresql@17/server.log \
  -o "-p 5433" start
/opt/homebrew/opt/postgresql@17/bin/createdb -p 5433 ship2shore

# 2. Python env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env   # DATABASE_URL already points at localhost:5433/ship2shore

# 4. Create the schema (enables the pgvector extension + tables)
python3 cli.py init-db
```

## Usage

```bash
# Ingest from the built-in free sources
python3 cli.py ingest --source arxiv          # runs the seed queries (below) — omit --query for this
python3 cli.py ingest --source wikipedia
python3 cli.py ingest --source maib --max-results 30       # UK casualty reports, via gov.uk's Atom feed
python3 cli.py ingest --source pdf --config ingest/sources.yaml   # NTSB reports + anything you curate

# Ingest your own local files — PDF, TXT, Markdown, HTML, Word, Excel, or PowerPoint
python3 cli.py ingest --source file --path "./docs/**/*"

# Ask a question (hybrid dense+keyword retrieval, then Claude if ANTHROPIC_API_KEY is set)
python3 cli.py ask "What drives container freight rate volatility?"

# Just retrieve passages, no generation
python3 cli.py ask "bill of lading vs sea waybill" --no-generate

# Export the answer as a compact report — small enough to attach to or paste
# straight into an email (no external assets, a few KB)
python3 cli.py ask "what caused the Dali allision?" --export briefing.html
python3 cli.py ask "what caused the Dali allision?" --export briefing.txt   # plain-text body instead
```

## How it works

```
ingest/sources.py       -> fetches raw documents (arXiv API, Wikipedia API, MAIB Atom feed, PDF URLs)
ingest/loaders.py        -> loads local files instead — PDF, TXT/MD, HTML, DOCX, XLSX, PPTX
ingest/chunk.py            -> splits documents into overlapping word-window chunks
ingest/embed.py              -> embeds chunks locally (sentence-transformers)
ingest/ingest.py               -> orchestrates fetch -> chunk -> embed -> upsert into pgvector
retrieval/retriever.py           -> hybrid retrieval: dense cosine + Postgres full-text, fused via RRF
retrieval/sqlite_store.py         -> same hybrid retrieval against the vessel-side SQLite snapshot
rag/pipeline.py                     -> builds a cited prompt from top-k chunks, calls Claude (optional)
rag/export.py                         -> renders an answer + sources as a compact HTML/text report
db/schema.sql                           -> documents + chunks tables, ivfflat cosine + GIN full-text index
ingest/export_sqlite.py                   -> snapshots the Postgres corpus into a single portable SQLite file
```

Retrieval fuses two rankings via [Reciprocal Rank
Fusion](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) — the same
pattern used for maritime accident-report retrieval in "Multi-Field Hybrid RAG
for Maritime Accident Root Cause Analysis" (arXiv 2606.13249): dense embedding
similarity finds conceptually related passages, keyword search catches exact
terms (vessel names, regulation numbers, IMO numbers) that embeddings can miss.

## Sources

| `--source` | What | License |
|---|---|---|
| `arxiv` | Seed queries (below) if `--query` is omitted, else your own search | arXiv non-exclusive license |
| `wikipedia` | A curated list of maritime-topic articles | CC BY-SA 4.0 |
| `maib` | UK Marine Accident Investigation Branch reports, discovered via `gov.uk/maib-reports.atom` | Open Government Licence v3.0 |
| `ntm` | UKHO ADMIRALTY weekly Notices to Mariners bulletin (the main booklet, not the per-chart correction PDFs) | UKHO/ADMIRALTY — free to download for navigational use; verify terms before redistribution |
| `pdf` | Anything in `ingest/sources.yaml` — seeded with NTSB marine accident reports | varies; NTSB reports are U.S. government works (public domain, 17 U.S.C. §105) |
| `file` | Your own local files — see `--path` above | whatever license the file itself carries — verify before ingesting |

NTSB has no stable public feed like MAIB's Atom feed (its search UI, CAROL, is a
private JS API) — report URLs there are curated by hand. Find more at
[data.ntsb.gov/carol-main-public](https://data.ntsb.gov/carol-main-public/basic-search)
(Mode = Marine); report PDFs live at a predictable path,
`ntsb.gov/investigations/AccidentReports/Reports/MIR####.pdf`.

UKHO's weekly Notices to Mariners page (`msi.admiralty.co.uk/NoticesToMariners/Weekly`)
issues a fresh download token per page load, so `fetch_ntm()` is a two-step
fetch (load the index page, then download using that token) rather than a
stable feed — and the download itself has been observed to intermittently
drop mid-transfer from this network, which is why `fetch_pdf()` now retries
with backoff (see `ingest/sources.py`).

**Formats with no public source to crawl.** DNV's class rules (RU-SHIP) are
free and public but distributed only as whole-edition ZIP archives, not
individually crawlable chapter links — download an edition from
[rules.dnv.com](https://rules.dnv.com/servicedocuments/dnvpm/packages?category=rulesship),
extract it, and ingest the PDFs you want with `--source file`. PMS (planned
maintenance system) manuals, SIRE 2.0/CDI vetting reports, and statutory
certificates (SOLAS/MARPOL/ISM/ISPS) are per-vessel/per-company private
documents by nature — there is no public corpus of these to fetch, so
`--source file` is the only ingestion path for them, by design.

`ingest/sources.py:DEFAULT_ARXIV_QUERIES` covers general shipping/logistics
literature *and* casualty/accident-analysis literature specifically (root cause
analysis, collision risk, PSC detention prediction, VTS/autonomous-ship safety,
human-factors analysis) — the market survey found this was the most active
academic RAG sub-area, well ahead of commercial deployment in the same domain.

## Adding more literature

Edit `ingest/sources.yaml` — add any publicly accessible PDF or HTML URL (IMO
circulars that are public, port authority reports, MARAD/UNCTAD publications,
industry white papers you have the right to ingest). Run
`python3 cli.py ingest --source pdf --config ingest/sources.yaml` to pull them in.
Respect each source's license/terms — this project only ingests sources that are
freely and legally accessible; it does not scrape paywalled or ToS-restricted
sites.

## Shipboard deployment

Vessels are not offices: no dedicated database server, often no GPU, and
connectivity is expensive, low-bandwidth satellite (VSAT/FleetBroadband) rather
than always-on internet — not a place to run live ingestion or depend on a
reachable Postgres server. This project splits accordingly:

| Tier | Where | Storage | Ingestion | Generation |
|---|---|---|---|---|
| **Shore** | office/shore-based server | Postgres + pgvector | Live (`cli.py ingest`) | Claude, if online |
| **Vessel** | onboard PC, offline | one SQLite file (`cli.py export-sqlite`) | None — read-only snapshot | Extractive only (no network needed) |
| **Vessel, in port / satellite window** | onboard PC, intermittently online | same SQLite file, periodically refreshed | None | Claude, if reachable |

Workflow: ingest and re-index shore-side as usual, then run
`python3 cli.py export-sqlite` to produce one file (a few MB for a corpus like
this one) and copy it aboard — USB at a port call, or over a compressed
low-bandwidth sync during a satellite window, the same way ECDIS chart updates
already reach most vessels. Onboard, set `STORAGE_BACKEND=sqlite` and
`SQLITE_PATH=/path/to/ship2shore.sqlite3` in `.env`; `cli.py ask` then needs
nothing else — no Postgres, no network — to retrieve and cite passages. `sqlite-vec`
is a pure C extension with no server process, and the embedding model
(`all-MiniLM-L6-v2`) is ~90MB and runs on CPU, so the whole retrieval path fits
comfortably on a low-power shipboard PC.

## Not yet done

- No web UI — CLI only.
- No incremental re-crawl/freshness tracking (documents are upserted by URL; no
  change detection yet).
- No chunk-level citation verification (unlike this user's other research repos,
  there is no `cite_check.py` wired in here yet).
- No automated NTSB crawler (CAROL's API isn't public/documented — see Sources).
- Citation traceability is source-link only; no per-paragraph / regulation-version
  tracking yet (the DNV RuleAgent / Vibylabs temporal-knowledge-graph pattern from
  the market survey is a documented future direction, not implemented).
- `--export` writes a report file — it does not send email itself. Attach or
  paste it into your mail client of choice.
