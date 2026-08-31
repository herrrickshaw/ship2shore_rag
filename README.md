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

See [ARCHITECTURE.md](ARCHITECTURE.md) for a structural map of the system
(data/application/technology layers, and how the pipeline evolved) —
this file is setup/usage, that one is "how does this actually fit together."

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
python3 cli.py ingest --source ntsb --max-results 30        # US marine reports, via CAROL's search API
python3 cli.py ingest --source pdf --config ingest/sources.yaml   # anything you curate by hand

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

# Structure the generated answer as an ordered, cited checklist instead of prose
python3 cli.py ask "steps for enclosed space entry" --checklist

# Shortcut: build a navigational/chokepoint/regulatory question for a port or strait
python3 cli.py ask --port "Strait of Hormuz" --export briefing.html

# Job-hazard brief — similar past incidents + every regulation instrument
# mentioned across them, deduplicated (retrieval only, not a risk score)
python3 cli.py hazard-brief "enclosed space entry on a chemical tanker"
```

## How it works

```
ingest/sources.py       -> fetches raw documents (arXiv, Wikipedia, MAIB Atom feed, NTSB CAROL API, PDF URLs)
ingest/loaders.py        -> loads local files instead — PDF, TXT/MD, HTML, DOCX, XLSX, PPTX
ingest/chunk.py            -> splits documents into overlapping word-window chunks
ingest/embed.py              -> embeds chunks locally (sentence-transformers)
ingest/freshness.py           -> content_hash so re-ingesting a changed URL updates it in place
ingest/regulation_refs.py      -> extracts real IMO/CFR regulation references from chunk text
ingest/ingest.py                -> orchestrates fetch -> chunk -> embed -> upsert (postgres or sqlite)
retrieval/retriever.py            -> hybrid retrieval: dense cosine + Postgres full-text, fused via RRF
retrieval/sqlite_store.py          -> same hybrid retrieval against the vessel-side SQLite snapshot
retrieval/rerank.py                  -> cross-encoder scores + sorts the candidate pool (no cut)
retrieval/diversify.py                 -> final top-k cut: per-source cap + near-duplicate skip
retrieval/query_log.py                   -> appends one JSON line per ask() call to query_log.jsonl
rag/pipeline.py                            -> builds a cited prompt from top-k chunks, calls Claude (optional)
rag/cite_check.py                            -> flags out-of-range / weakly-grounded [n] citations
rag/export.py                                  -> renders an answer + sources as a compact HTML/text report
db/schema.sql                                    -> documents + chunks tables, ivfflat cosine + GIN full-text index
ingest/export_sqlite.py                            -> snapshots the Postgres corpus into a portable SQLite file
eval/evaluate.py                                     -> Recall@k / MRR against eval/queries.yaml (cli.py eval)
webui/server.py                                        -> small read-only FastAPI app (cli.py serve)
```

Retrieval fuses two rankings via [Reciprocal Rank
Fusion](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) — the same
pattern used for maritime accident-report retrieval in "Multi-Field Hybrid RAG
for Maritime Accident Root Cause Analysis" (arXiv 2606.13249): dense embedding
similarity finds conceptually related passages, keyword search catches exact
terms (vessel names, regulation numbers, IMO numbers) that embeddings can miss.
RRF's fused order is then rescored by a local cross-encoder
(`cross-encoder/ms-marco-MiniLM-L-6-v2`) over a wider candidate pool — RRF
only knows *where* each side ranked a chunk, not how relevant it actually is
to the query, and a cross-encoder reading (query, passage) pairs jointly is
usually the single biggest relevance gain in a hybrid pipeline. Disable with
`ask --no-rerank` / `ask(..., rerank=False)` to fall back to RRF order as-is.
The final top-k cut then goes through a diversity filter
(`retrieval/diversify.py`): caps results per source document and skips
near-duplicate passages, so a handful of near-identical chunks from one
report can't crowd out everything else. `ask --since YYYY-MM-DD` /
`--source-filter {arxiv,wikipedia,maib,ntm,pdf,file}` narrow retrieval by
publish date or ingestion source (only arxiv/maib carry a real publish
date; a `--since` filter excludes everything else). Retrieval quality is
measurable, not just eyeballed — `cli.py eval` runs Recall@k/MRR from
`eval/queries.yaml` against the real corpus, rerank on vs. off.

## Sources

| `--source` | What | License |
|---|---|---|
| `arxiv` | Seed queries (below) if `--query` is omitted, else your own search | arXiv non-exclusive license |
| `wikipedia` | A curated list of maritime-topic articles | CC BY-SA 4.0 |
| `maib` | UK Marine Accident Investigation Branch reports, discovered via `gov.uk/maib-reports.atom` | Open Government Licence v3.0 |
| `ntm` | UKHO ADMIRALTY weekly Notices to Mariners bulletin (the main booklet, not the per-chart correction PDFs) | UKHO/ADMIRALTY — free to download for navigational use; verify terms before redistribution |
| `ntsb` | US NTSB marine accident reports, discovered via CAROL's search API | U.S. government work — public domain (17 U.S.C. §105) |
| `pdf` | Anything in `ingest/sources.yaml` — seeded with a handful of NTSB reports and arXiv papers found by name rather than through the seed queries | varies; verify per entry |
| `file` | Your own local files — see `--path` above | whatever license the file itself carries — verify before ingesting |

NTSB has no *documented* public API, but CAROL's search UI
(`data.ntsb.gov/carol-main-public`) is backed by a plain, unauthenticated JSON
endpoint (`api/Query/Main`, after a throwaway `api/Session/CreateSession`
call) that `fetch_ntsb()` queries directly (`Mode=Marine`), discovering and
downloading report PDFs (`MIR`/`MAB`/`MAR`-prefixed) rather than relying on
hand-curated URLs. Verified live 2026-08-26 (~450 real marine reports
discoverable this way); if NTSB changes CAROL's internals this may need
re-verifying — the small hand-picked set in `ingest/sources.yaml` is kept as
a fallback either way.

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
industry white papers you have the right to ingest). Entries are PDFs by
default (`pypdf`, entirely local); add `type: html` for a non-PDF page —
those are fetched as clean markdown via [Jina AI
Reader](https://r.jina.ai/) (free tier, no API key) instead of raw HTML
scraping. Run `python3 cli.py ingest --source pdf --config
ingest/sources.yaml` to pull them in. Respect each source's license/terms —
this project only ingests sources that are freely and legally accessible;
it does not scrape paywalled or ToS-restricted sites. `type: html` routes
the URL through Jina's servers, which is fine for public pages but not
appropriate for anything under restricted redistribution terms — use
`--source file` for those instead (never leaves this machine).

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

A ready-to-copy snapshot (with checksum and corpus composition) is committed
at [`snapshots/`](snapshots/README.md) — a real vessel deployment would
generate its own via `export-sqlite` rather than rely on a committed one, but
it's there as a working example and for quick testing.

## Operations module

Everything above is the literature/RAG side — free public documents, answered
via retrieval. Alongside it, a separate **operations module** tracks the
transactional records a vessel actually generates day to day: vessel
particulars, crew, logbooks, engineering/EPC records, and fuel. It's a
distinct concern from the RAG corpus (structured records vs. free-text
literature) but shares this project's two defining constraints: it must run
offline on a vessel, and it must not pretend to be bigger than it is.

### Entities

| Table | What | CLI |
|---|---|---|
| `users` | Crew/staff identities + role, for attribution and access control | `cli.py user add/list` |
| `vessels` | Ship particulars — IMO number, flag, type, tonnage, main engine | `cli.py vessel add/list` |
| `crew` | Seafarer onboarding — rank, nationality, STCW cert + expiry, sign-on/off | `cli.py crew add/list/signoff` |
| `log_entries` | Master/captain's log, deck log, engine log — timestamped, geolocated free text | `cli.py log add/list` |
| `equipment` | Engineering asset registry (main engine, generators, etc.) per vessel | `cli.py equipment add/list` |
| `spare_parts` | EPC (Electronic Parts Catalog) — part numbers/stock tied to equipment | `cli.py parts add/list` |
| `maintenance_jobs` | Repair/maintenance history — job type, description, running hours, parts used | `cli.py maintenance add/list` |
| `fuel_log` | Bunkering/consumption/ROB events | `cli.py fuel add/list` |
| `purchase_orders` | Procurement (purchase-to-pay) — status workflow, tied to the EPC parts catalog | `cli.py procurement add/list/approve/status` |
| `drydock_events` | Dry-docking — yard, scope, planned/actual dates, cost | `cli.py drydock add/list` |
| `safety_incidents` | QHSE — near-miss/incident/audit/inspection reports, open/closed | `cli.py safety report/list/close` |

Three composition commands span both the operations tables above and the
literature corpus (not new tables, not new ingestion — they join what
already exists):

| Command | What |
|---|---|
| `cli.py training-gaps` | Crew with an STCW cert expiring soon, each cited against the STCW convention text already ingested |
| `cli.py fleet status` / `GET /fleet/status` | Read-only cross-vessel rollup — open incidents by severity, certs expiring, upcoming dry-dockings |
| `cli.py safety report --find-similar` | After filing a report, retrieves similar past incidents from the ingested corpus |

### IAM — scoped to what a CLI tool actually needs

This is **not** web authentication — no passwords, no sessions, no login
screen. That would be the wrong shape of complexity for a local CLI tool, the
same way a full Postgres server is the wrong shape for a vessel's onboard PC.
Instead, IAM here means exactly two things:

1. **Identity**: pass `--user "<name>"` on any command (or set
   `SHIP2SHORE_USER` in `.env`), matched against a name registered via
   `cli.py user add`. This is who a log entry or maintenance job gets
   attributed to.
2. **Authorization**: a small role → allowed-actions table in `ops/auth.py`.
   A `deck_crew` user cannot write a captain's log entry or add a vessel; a
   `chief_engineer` can log maintenance and fuel but not sign crew on/off.
   Unlisted actions (all the `list` commands) are unrestricted — read access
   isn't the thing worth gating here.

Roles: `master`, `chief_engineer`, `officer`, `deck_crew`, `engine_crew`,
`shore_staff`. See `ops/auth.py:PERMISSIONS` for the full action → role map —
it's a plain dict, easy to extend.

```bash
python3 cli.py user add "Captain Ahab" --role master
python3 cli.py user add "Deck Hand" --role deck_crew

python3 cli.py vessel add "MV Example" --imo 9999999 --type "container ship" --user "Captain Ahab"
python3 cli.py log add "MV Example" captain "Departed port, all clear." --lat 51.9 --lon 4.5 --user "Captain Ahab"
python3 cli.py log add "MV Example" captain "..." --user "Deck Hand"   # denied — wrong role

python3 cli.py equipment add "MV Example" "Main Engine" --manufacturer "MAN B&W" --user "Chief Engineer"
python3 cli.py parts add 1 "PN-9001" "Cylinder liner" --qty 2 --user "Chief Engineer"
python3 cli.py maintenance add 1 repair "Replaced cylinder liner #4" --hours 34500 --parts-used "PN-9001 x1" --user "Chief Engineer"
python3 cli.py fuel add "MV Example" VLSFO bunkering 800 --rob 1450 --location Rotterdam --user "Chief Engineer"

# Procurement — request/approve workflow, tied to the parts catalog above
python3 cli.py procurement add "MV Example" "PN-9001 Cylinder liner x2" --supplier "MAN Energy Solutions" --cost 8500 --currency USD --user "Chief Engineer"
python3 cli.py procurement approve 1 --user "Captain Ahab"   # only master/shore_staff can approve

# Dry-docking
python3 cli.py drydock add "MV Example" --yard "Keppel Shipyard" --start 2027-03-01 --end 2027-03-20 --scope "5-year special survey" --user "Captain Ahab"

# QHSE — anyone can report, no --user role restriction; only master/shore_staff can close
python3 cli.py safety report "MV Example" near_miss "Loose grating, tripping hazard" --severity medium --user "Deck Hand"
python3 cli.py safety report "MV Example" incident "Steering gear failure" --severity critical --find-similar
python3 cli.py safety close 1 --corrective-action "Grating re-secured and inspected" --user "Captain Ahab"

# Crew whose STCW cert is expiring soon, cited against the ingested STCW convention text
python3 cli.py training-gaps --days 30

# Read-only cross-vessel rollup — open incidents, cert expiries, drydocks
python3 cli.py fleet status
```

### Offline-first, same as the literature corpus

`ops/store.py` dispatches on the same `STORAGE_BACKEND` switch as retrieval:
Postgres shore-side, a separate single-file SQLite database (`OPS_SQLITE_PATH`,
default `ship2shore_ops.sqlite3`) vessel-side. This one's deliberately *not*
the same file as the literature snapshot (`SQLITE_PATH`) — that file is a
read-only distributed copy regenerated from Postgres; this one is live data
being written to at sea, and conflating "distributed snapshot" with "source
of truth being written to" would be a real design mistake, not a simplification.
There's no sync-back-to-shore mechanism yet (see below).

### REST API

`api.py` is a FastAPI wrapper around `ops/store.py` — everything the CLI does,
as HTTP, for a frontend to call. Same IAM as the CLI: pass the acting user's
name as an `X-User` header instead of `--user`; unauthenticated requests are
treated as no user (denied on any restricted action, same as the CLI with no
`--user`/`SHIP2SHORE_USER` set).

**`X-User` is attribution, not authentication** — a self-reported name with
nothing cryptographic behind it, which is fine for a trusted local CLI but
not for an API reachable from the internet. The actual access gate is
`X-API-Key`: every request needs a matching key. If `API_KEY` isn't set in
the environment, one is generated and printed once at startup — the API is
never silently open. Set your own `API_KEY` before deploying anywhere public,
and share it only with whoever should be able to use the app.

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
export API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
uvicorn api:app --reload --port 8010
# interactive docs at http://localhost:8010/docs — but /docs itself also
# requires X-API-Key on every call it makes, so use "Authorize" in the UI
curl -H "X-API-Key: $API_KEY" http://localhost:8010/vessels
```

Endpoints mirror the CLI's resource shape — `POST/GET /vessels`,
`POST/GET /vessels/{name_or_imo}/log`, `POST/GET /equipment/{id}/parts`,
`POST /procurement/{id}/approve`, `POST /safety/{id}/close`, etc. — see
`/docs` for the full interactive list, or `api.py` directly (it's one file,
organized in the same order as `ops_cli.py`). `GET /fleet/status` is the one
cross-vessel exception (see "Entities" above); `POST .../safety` accepts an
optional `?find_similar=true` to retrieve similar past incidents inline.

**Container image**: `Dockerfile` + `requirements-api.txt` build a slim image
(just `api.py` + `ops/` — none of the RAG-ingestion side's heavy deps like
sentence-transformers/torch). `.github/workflows/docker.yml` builds and
pushes it to `ghcr.io/<owner>/ship2shore_rag/ops-api` on every push to `main`
that touches the API code, so a deployable public image always exists —
independent of whether the API itself is running anywhere yet:

```bash
docker pull ghcr.io/herrrickshaw/ship2shore_rag/ops-api:latest
docker run -p 8010:8010 -e API_KEY="$API_KEY" -e DATABASE_URL="$DATABASE_URL" ghcr.io/herrrickshaw/ship2shore_rag/ops-api:latest
```

**Not yet done: actually running this somewhere public.** The image is
publishable and pullable; nothing hosts and runs it continuously with a
public URL and a publicly reachable Postgres yet. `fly.toml` is written and
ready (Fly.io, `sin` region, scales to zero when idle to keep cost down), but
actually deploying needs steps only the account owner can do — I can't
create a Fly.io account, add a payment method, or complete the browser-based
`fly auth login`. **Fly.io has no free tier as of 2026** — a card is
required to sign up, and even the cheapest path costs something monthly, so
this is a real decision for whoever's paying, not something to default into.

To deploy once you're ready:

```bash
brew install flyctl        # already done in this environment
fly auth login              # opens your browser — this step is yours to do
fly launch --no-deploy       # picks up fly.toml, creates the app, skips first deploy

# Cheapest Postgres path: an unmanaged Fly Postgres app (a few $/month for a
# small single-node instance) rather than Fly's Managed Postgres ($38+/month) —
# reasonable for this project's scale, not for a production fleet system.
fly postgres create --name ship2shore-ops-db --initial-cluster-size 1 --vm-size shared-cpu-1x --volume-size 3
fly postgres attach ship2shore-ops-db -a ship2shore-ops-api   # wires DATABASE_URL automatically

fly secrets set API_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')" -a ship2shore-ops-api
fly deploy -a ship2shore-ops-api

# then run `python3 cli.py init-db` once (or the equivalent SQL) against the
# new Postgres to create the ops tables — the app doesn't self-migrate
```

After that, tighten `allow_origins` in `api.py` from `"*"` to the actual
frontend origin, and update the Lovable project's `API_BASE` (in
`src/lib/api.ts`, or via the `s2s.apiBase` localStorage override already
built into it) to the new `https://ship2shore-ops-api.fly.dev` URL.

**Deployment caveat, stated plainly:** this only listens on `127.0.0.1` by
default and isn't deployed anywhere public. A frontend hosted elsewhere (e.g.
on Lovable) cannot reach `localhost` on your machine — for that to work, this
API needs to run somewhere with a public URL (a small VM, Fly.io, Render,
etc.), with `DATABASE_URL` pointed at a reachable Postgres and CORS
(`allow_origins` in `api.py`) tightened to the actual frontend origin instead
of `*`. That deployment step isn't done yet — running it locally is enough
for development and for driving a frontend that also runs locally.

### Honest scope

- **Not multi-vessel fleet software.** `cli.py fleet status` / `GET
  /fleet/status` aggregate a read-only snapshot across vessels (open
  incidents, cert expiries, drydocks) — but nothing here syncs vessel →
  shore, and there's no write path or per-fleet permission model. A real
  fleet operator needs that; it's still a substantial feature this project
  doesn't have.
- **Not a replacement for statutory logs.** A ship's official logbook has
  legal requirements (format, retention, inspection) this tool doesn't
  attempt to satisfy — treat `log_entries` as a searchable digital
  supplement, not the vessel's legal record of account.
- **The captain's-log/EPC pattern is a starting shape, not a finished
  product** — it covers the entities asked for (IAM, seafarer onboarding,
  ship particulars, master/captain's log, EPC + repair history, fuel log,
  procurement, dry-docking, QHSE/safety reporting) at the depth a CLI tool
  can reasonably carry, matching the shape of the commercial systems
  surveyed (V.Group ShipSure, SpecTec AMOS, BASSnet, ShipNet, DNV
  ShipManager) without their scale or their proprietary data.
- **Still explicitly not covered**, per that same survey: crew payroll
  (financial/compliance-heavy, a poor fit here), mobile apps (this is a CLI
  tool), and condition-based maintenance / hull-fuel-performance analytics
  (a different category of feature — real-time sensor data + ML, not a CRUD
  table like everything else in this module).

## Web UI

`cli.py serve` starts a small dedicated FastAPI app (`webui/`, separate from
`api.py`'s ops REST API — read-only, no credentials needed) serving a
single self-contained page (`webui/index.html`, no build step) at
`http://127.0.0.1:8020` by default. Binds to localhost only unless
`WEBUI_HOST` is set explicitly — there's no auth here, so it must not be
reachable from the network by accident. Works against either backend
(`STORAGE_BACKEND=postgres` or `sqlite`), same as the CLI.

## Ingestion service

`cli.py serve-ingest` starts a small FastAPI microservice
(`ingest_service/`) that turns every registered source in
`ingest/registry.py` into one uniform HTTP control plane, so the corpus
keeps improving after deployment instead of being frozen at whatever was
ingested manually beforehand:

- `GET /sources` — every registered source, its polling interval, and its
  next scheduled run.
- `POST /sources/{name}/ingest` — trigger an immediate run for one source
  in the background (the same code path a scheduled run uses).
- `GET /runs?limit=20` — recent run history (source, trigger, fetched/
  ingested counts, errors) from `ingest_runs.jsonl`.

An [APScheduler](https://apscheduler.readthedocs.io/) background scheduler
polls every source on its own cadence (arxiv/maib/ntsb/pdf daily,
wikipedia/ntm weekly by default — see each plugin's `interval_minutes` in
`ingest/registry.py`) — honest scheduled polling, not literal real-time/
event-driven streaming, since none of the underlying sources (arXiv's
API, MAIB/NTM's feeds, NTSB's CAROL endpoint) offer a push mechanism to be
real-time *about*. `--source file` is intentionally not schedulable — it
has no default path to poll.

Adding a new source means adding one entry to `ingest/registry.py`'s
`REGISTRY` — the CLI, this service, and its scheduler all pick it up
automatically; nothing else changes. Localhost-only by default
(`INGEST_SERVICE_HOST` to opt into anything else), same convention as the
web UI — this service *writes* to the corpus, so unlike the web UI its
default posture matters even more.

## Regulation-reference extraction

Citation traceability is source-link + per-citation grounding check
(`rag/cite_check.py`) *plus* per-paragraph regulation references:
`ingest/regulation_refs.py` extracts real IMO instrument mentions (SOLAS,
MARPOL, STCW, COLREG, ISM/ISPS Code, MLC, BWM, SAR, Load Lines — with
Annex/Chapter/Regulation detail and nearby amendment years, when present)
and US CFR citations already present in chunk text, stored per-chunk
(`chunks.regulation_refs`, both backends) and surfaced in retrieval results
and `check_citations()`'s output. Run `python3 -m
ingest.backfill_regulation_refs` after upgrading to compute it for chunks
ingested before this existed — freshness tracking correctly skips
re-processing unchanged text, which also means it won't retroactively add
new derived metadata on its own.

This is real extraction of what's already stated in the text, not a
temporal knowledge graph modeling which version of a regulation supersedes
which (the DNV RuleAgent / Vibylabs pattern from the market survey) — that
remains a materially larger, undertaken future direction, not implemented.

## Not yet done

- `--export` writes a report file — it does not send email itself. Attach or
  paste it into your mail client of choice.
