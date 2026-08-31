# Architecture

This document structures ship2shore_rag through four lenses, each grounded
in a real, cited source rather than described in the abstract: **TOGAF's
four architecture domains**[^togaf] (what the system is, layer by layer),
the general **SDLC**[^sdlc] (how it was engineered), the domain-specific
**Data Analytics Lifecycle**[^dsbda] (the same build, from a data-pipeline
angle), and **Kaizen**[^kaizen] (how it keeps improving). Every claim below
names an actual file, table, or measured number — see "References" at the
bottom for full citations.

## TOGAF view: four architecture domains[^togaf]

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
ingest/registry.py             -> one uniform interface over every source (see below)
ingest/sources.py, loaders.py  -> fetch (arxiv/wikipedia/maib/ntsb/ntm/pdf/html/file)
ingest/chunk.py, embed.py      -> chunk + embed locally
ingest/ingest.py               -> upsert, freshness-aware (postgres or sqlite)
        |
retrieval/retriever.py  -> RRF fusion (dense cosine + sparse keyword)
retrieval/rerank.py     -> cross-encoder rescoring of the candidate pool
retrieval/diversify.py  -> final top-k cut: per-source cap + dedup
        |
rag/pipeline.py           -> cited prompt, optional Claude generation (prose or --checklist)
rag/cite_check.py         -> flags out-of-range / weakly-grounded citations
rag/hazard_brief.py       -> job description -> similar passages + deduped regulation_refs
rag/similar_incidents.py  -> incident description -> similar past reports (opt-in, ops calls it)
rag/training_gaps.py      -> ops.store.list_expiring_certs() joined against STCW passages
        |
cli.py (CLI) | webui/ (browser, read-only) | ingest_service/ (write, scheduled+on-demand) | api.py (ops REST)
```

Every stage above is independently swappable because each does exactly one
job — this is what let reranking, diversity filtering, and metadata
filtering each land as an isolated change to `retriever.py`'s pipeline
this session without touching the stages around them.

`ingest/registry.py` is the same principle applied one layer up: before it
existed, adding a source meant editing an if/elif chain in `cli.py`
(`if args.source == "arxiv": ... elif ...`) — data-type-specific dispatch
baked into the CLI itself. Every fetcher now registers as a
`SourcePlugin(name, fetch, description, interval_minutes)`; `cli.py`,
`ingest_service/server.py`'s scheduler, and its `/sources`/`/runs`
endpoints all read from the same `REGISTRY` dict, so a new source is one
registry entry, not N call sites to update. This is what "moving from
data-type-specific processing to generic processing" concretely means
here — a dispatch table, not a rewrite of every source's actual fetch
logic (arXiv's API shape and NTSB's CAROL API shape are still genuinely
different; the registry doesn't pretend otherwise, it just gives every
difference a uniform *call* shape).

`ingest_service/` is the deployment-time half: an HTTP control plane over
the same registry, with an APScheduler background loop that polls each
source on its own cadence so the corpus keeps improving with new data
after the system is live, not just at whatever was ingested manually
before launch. This is honest scheduled polling, not literal real-time/
event-driven streaming — none of arXiv's API, MAIB/NTM's feeds, or NTSB's
CAROL endpoint offer a push/webhook mechanism to be real-time *about*, so
periodic polling close to each source's own actual update cadence is what
"real-time" correctly means for this specific set of sources. See README
"Ingestion service" for the endpoints.

### Technology Architecture — what it runs on

Local-first by deliberate choice at every layer, not just the obvious one:
`sentence-transformers` for embeddings (not an embedding API),
`cross-encoder/ms-marco-MiniLM-L-6-v2` for reranking (same reasoning),
Claude generation is optional (extractive fallback works with zero API
calls), Jina AI Reader is the one exception — an external service, used
only for public HTML pages in `sources.yaml`, explicitly not for anything
under restricted redistribution terms (`--source file` stays fully local
for those). FastAPI + uvicorn for `api.py`, `webui/server.py`, and
`ingest_service/server.py` — three small independently-runnable services,
one write surface each with a distinct trust model (ops CRUD +
API-key auth, read-only Q&A + no auth, corpus writes + localhost-only), not
one monolith with internal mode-switches. APScheduler (`BackgroundScheduler`,
its own thread pool — doesn't block FastAPI's async event loop) for
`ingest_service`'s polling. Docker/GHCR for the ops API; Fly.io deploy
config exists but requires the user's own account setup.

## SDLC: the general software process, applied here

Lemke's SDLC thesis (2018) enumerates six phases — planning and requirement
analysis, design and development, implementation, testing, integration,
maintenance[^sdlc] — built and applied to a real small web app in that
thesis, and equally real here at a larger scale:

1. **Planning and requirement analysis** — the market/literature survey
   that found the actual gap (self-hostable, legally-open-only RAG) before
   any code existed.
2. **Design and development** — the architecture decisions in the sections
   above: shore/vessel split, hybrid retrieval, dual-backend storage.
3. **Implementation** — the modules themselves: `ingest/`, `retrieval/`,
   `rag/`, `ops/`, `webui/`, `cli.py`.
4. **Testing** — 92 pytest tests (`tests/`) plus `eval/evaluate.py`'s
   retrieval-specific Recall@k/MRR harness, which ordinary unit tests can't
   substitute for (they check code correctness, not retrieval quality).
5. **Integration** — the branch-gate step every multi-part change went
   through this session: leaf-level work verified independently, then
   wired together (`cli.py`, CI whitelist, README) and re-verified as a
   whole — see `gates/node-1.md` for a concrete instance of this phase
   done explicitly, not implicitly.
6. **Maintenance** — `content_hash`-based freshness tracking
   (`ingest/freshness.py`) so re-ingesting a changed source updates the
   corpus in place instead of going silently stale; `CHANGELOG.md` as the
   maintenance log.

## Data Analytics Lifecycle: how this was actually built[^dsbda]

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

## Kaizen: the improvement loop, not just the pipeline[^kaizen]

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

Okpala, Ezeanyim & Nwamekwe's review of Kaizen in manufacturing makes a
point that generalizes past its own domain: standardized processes are
what make Kaizen improvements *measurable* in the first place —
"[w]ithout standardization, it would be challenging to gauge the impact
of Kaizen activities."[^kaizen] `eval/evaluate.py` is that standardization
here: a fixed, repeatable measurement (Recall@k/MRR against the same 15
queries) is what let reranking's and dedup's actual effect be stated as
numbers (0.633→0.933 MRR; 0.93→0.47→0.93 recall through the
quick_ratio→ratio() fix) instead of "seems better."

## Where this document stops

This is a structural map, not a tutorial — see [README.md](README.md) for
setup/usage, [CHANGELOG.md](CHANGELOG.md) for the decision history, and
`PLAN.md`/`gates/` for the evidence trail behind the largest single batch
of changes (the orchestrated "close the remaining gaps" build).

## References

[^togaf]: The Open Group. *The TOGAF® Standard, 10th Edition* (document
    C220). Published April 2022. <https://pubs.opengroup.org/togaf-standard/>

[^sdlc]: Lemke, Gillian. "The software development life cycle and its
    application." Senior Honors Theses and Projects, 589. Eastern Michigan
    University, Computer Science (advised by Dr. Krish Narayanan and Dr.
    Augustine Ikeji), 2018. <https://commons.emich.edu/honors/589>

[^dsbda]: Dietrich, D., Heller, B., & Yang, B. (EMC Education Services).
    *Data Science & Big Data Analytics: Discovering, Analyzing,
    Visualizing and Presenting Data*. Wiley, 2015. ISBN 978-1-118-87613-8.
    Chapter 2, "Data Analytics Lifecycle."

[^kaizen]: Okpala, Charles Chikwendu; Ezeanyim, Okechukwu Chiedu; &
    Nwamekwe, Charles Onyeka. "The Implementation of Kaizen Principles in
    Manufacturing Processes: A Pathway to Continuous Improvement."
    *International Journal of Engineering Inventions*, 13(7), 116–124,
    July 2024. Industrial/Production Engineering Department, Nnamdi
    Azikiwe University, Nigeria. <https://www.ijeijournal.com/papers/Vol13-Issue7/1307116124.pdf>
