# ship2shore_rag

A retrieval-augmented generation (RAG) system for maritime/ocean-freight shipping
knowledge — vessel operations, port logistics, bills of lading, freight economics,
and maritime regulation. It ingests literature from free, legal public sources
(arXiv papers, Wikipedia, UNCTAD's annual Review of Maritime Transport, and any
PDF/URL you add), embeds it locally, stores it in Postgres/pgvector, and answers
questions by retrieving relevant passages and (optionally) generating a cited
answer with Claude.

**Status:** early scaffold — ingestion + retrieval work end-to-end; generation is
optional and requires an Anthropic API key.

## Stack

- **Postgres + [pgvector](https://github.com/pgvector/pgvector)** — chunk storage and
  cosine-similarity search.
- **sentence-transformers (`all-MiniLM-L6-v2`)** — local, free, no API key needed for
  embeddings.
- **Claude (optional)** — generates a cited answer from retrieved passages. Without
  `ANTHROPIC_API_KEY` set, `ask` falls back to returning the raw ranked passages
  (extractive mode, still fully functional).

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
# Ingest from the built-in free sources (arXiv + Wikipedia + UNCTAD report list)
python3 cli.py ingest --source arxiv --query "container shipping logistics" --max-results 20
python3 cli.py ingest --source wikipedia
python3 cli.py ingest --source pdf --config ingest/sources.yaml

# Ask a question
python3 cli.py ask "What drives container freight rate volatility?"

# Just retrieve passages, no generation
python3 cli.py ask "bill of lading vs sea waybill" --no-generate
```

## How it works

```
ingest/sources.py   -> fetches raw documents (arXiv API, Wikipedia API, PDF URLs)
ingest/chunk.py      -> splits documents into overlapping word-window chunks
ingest/embed.py       -> embeds chunks locally (sentence-transformers)
ingest/ingest.py       -> orchestrates fetch -> chunk -> embed -> upsert into pgvector
retrieval/retriever.py  -> embeds a query, cosine-search top-k chunks in pgvector
rag/pipeline.py          -> builds a cited prompt from top-k chunks, calls Claude (optional)
db/schema.sql             -> documents + chunks tables, ivfflat cosine index
```

## Adding more literature

Edit `ingest/sources.yaml` — add any publicly accessible PDF or HTML URL (IMO
circulars that are public, port authority reports, MARAD/UNCTAD publications,
industry white papers you have the right to ingest). Run
`python3 cli.py ingest --source pdf --config ingest/sources.yaml` to pull them in.
Respect each source's license/terms — this project only ingests sources that are
freely and legally accessible; it does not scrape paywalled or ToS-restricted
sites.

## Not yet done

- No web UI — CLI only.
- No incremental re-crawl/freshness tracking (documents are upserted by URL; no
  change detection yet).
- No chunk-level citation verification (unlike this user's other research repos,
  there is no `cite_check.py` wired in here yet).
