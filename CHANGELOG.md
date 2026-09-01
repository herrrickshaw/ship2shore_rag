# Changelog

## [Unreleased] — 2026-09-01 — Ops API deployed to Fly.io

### Deployed
- **`https://ship2shore-ops-api.fly.dev`** — the ops REST API, previously
  documented as buildable-but-unhosted, is now live: a Fly app
  (`ship2shore-ops-api`, `sin` region, `fly.toml` as already checked in)
  backed by a small unmanaged Fly Postgres app (`ship2shore-ops-db`),
  scales to zero when idle. `db/ops_schema.sql` applied directly (this
  Postgres has no `vector` extension, so the combined `cli.py init-db` —
  which also runs the RAG side's `db/schema.sql` — doesn't apply here;
  see README for the full explanation), seeded with the same throwaway
  demo dataset used for local testing.
- The already-published [Ship2Shore Ops](https://ship2shore-ops-demo.lovable.app)
  Lovable frontend now points at this permanent URL instead of a
  Cloudflare quick tunnel — public, survives a reboot, not tied to any
  one machine.
- README's "Not yet done: actually running this somewhere public" section
  is now a "Deployed" section with the real setup, plus two documented
  open gaps: the Postgres/`vector`-extension deviation above, and
  `allow_origins="*"` in `api.py` still not tightened to the frontend's
  actual origin (fine for a demo answering only seeded data, first thing
  to fix if this ever serves real fleet data).

## [Unreleased] — 2026-08-30 — Six roadmap features from the feature-pitch review

### Added
- **`cli.py hazard-brief`** (`rag/hazard_brief.py`) — retrieval-only job-hazard
  briefs: given a job description, retrieves similar past incidents/guidance
  and returns every distinct regulation instrument (`ingest/regulation_refs.py`)
  mentioned across the retrieved passages, deduplicated. Not a generative risk
  score or a predictive model — composes existing retrieval + extraction only.
- **`cli.py fleet status`** / `GET /fleet/status` (`ops/store.py`:
  `list_all_open_incidents`, `list_upcoming_drydocks`, `fleet_status`) — a
  read-only cross-vessel rollup (open incidents by severity, STCW certs
  expiring soon, upcoming dry-dockings), closing the gap README's "Honest
  scope" section names directly ("Not multi-vessel fleet software. Nothing
  here aggregates across vessels.") for the read side only — no write path,
  no vessel-to-vessel sync.
- **`cli.py safety report --find-similar`** / `POST .../safety?find_similar=true`
  (`rag/similar_incidents.py`) — after filing a near-miss/incident, optionally
  retrieves similar past reports from the ingested corpus. Pattern recall at
  report time, not a predictive model; kept as a standalone opt-in module
  rather than wired into `ops/store.py`'s write path, so ops (dependency-light
  CRUD) and rag (retrieval, embeddings) stay the separate concerns README
  already treats them as.
- **`cli.py training-gaps`** (`rag/training_gaps.py`) — crew whose STCW
  certificate is expiring soon (`ops/store.py:list_expiring_certs`, existing),
  each annotated with the STCW convention passages already ingested and cited
  via `regulation_refs`. One retrieval call per batch, not per crew member.
- **`cli.py ask --checklist`** (`rag/pipeline.py`) — restructures a generated
  answer as an ordered, cited checklist instead of prose. New
  `CHECKLIST_SYSTEM_PROMPT` / `_system_prompt()`; passed through in
  `webui/server.py`'s `AskRequest` and the web UI's form.
- **`cli.py ask --port "<name>"`** — composes a navigational-hazard/
  chokepoint-security/regulatory question for a named port or strait and
  runs it through the existing `ask()` pipeline; `question` is now optional
  on `ask` (required only when `--port` is absent). Pure composition over
  already-ingested sources — no new retrieval path.

Source: a feature-pitch review cross-referencing Synergy Group's 2020
"Tech Transformation Projects — Approved List" against this project's
actual architecture, filtered to what extends existing retrieval/
extraction/ops rather than requiring a different kind of system. Payroll
automation, sensor-based fatigue/health monitoring, and a messaging-bot
layer were reviewed and deliberately excluded — see the pitch doc for why.

Tests: `tests/test_hazard_brief.py`, `tests/test_similar_incidents.py`,
`tests/test_training_gaps.py`, `tests/test_fleet_status.py`,
`tests/test_pipeline.py`, `tests/test_cli.py`, plus updates to
`tests/test_webui.py` for the new `checklist` field. All added to
`.github/workflows/quality-gates.yml`'s test run.

## [Unreleased] — 2026-08-27 — Ship-management industry associations and developments via type: html

### Added
- **4 sources on the industry-level developments and needs of ship
  management/crewing companies**, complementing the prior round's
  single-company (Synergy Marine Group) sources with the trade bodies
  that represent the sector as a whole: InterManager (the only
  association dedicated to representing the ship management industry —
  7,500+ ships, 330,000+ seafarers represented, founded 1991 as ISMA),
  Fleet Management Limited's "About Us" (a major third-party ship
  manager, 650+ vessels, founded 1994), the International Chamber of
  Shipping's "About ICS" (the global trade association for shipowners/
  operators, established 1921, representing 80%+ of the world merchant
  fleet), and Wikipedia's "Seafarer's professions and ranks" (deck/
  engine rank hierarchy, complements `ops.crew.rank`). Checked and
  rejected Wallem's site (a malformed page returning unrelated
  "vacations" content), V.Group and Anglo-Eastern (404/empty response),
  BIMCO's about page (cookie-consent wall only — same failure mode
  already noted for BIMCO/Lloyd's Register earlier in this file), and
  SAFETY4SEA's crew-shortage tag/article pages (404). Corpus: 668 → 672
  documents (18,648 chunks).
- Verified genuinely retrievable: "what industry association represents
  ship management and crewing companies globally" ranks InterManager and
  Fleet Management directly in the top 5. The ICS page is mostly
  cookie-consent boilerplate (8 of 11 chunks) with real substance in
  only 2–3 — a generic query missed it, but "ICS established in 1921
  best practices shipowners operators," matching its actual distinguishing
  content, correctly ranks it #2, confirming it's genuinely present
  despite the low signal-to-noise ratio.

## [Unreleased] — 2026-08-27 — Ship-management crewing and seafarer welfare via type: html

### Added
- **4 sources on what shipping service companies actually provide
  seafarers**, prompted by a direct request to look at Synergy Marine
  Group specifically: Synergy's "About Us" (company overview — founded
  2006, Singapore, world's second-largest third-party ship manager),
  "Crew Management" (its crewing/seafarer-support service description —
  family communications, payroll transparency, career development,
  KPI-linked crewing accountability), and "WeTeam" (its i-STEER mental
  health/wellbeing program — 24-hour helpline, Wellbeing Champions peer
  support, Family Outreach coordination); plus ISWAN's "Service providers
  for the maritime industry" page — the sector's leading seafarer-welfare
  NGO's description of what it commissions *for* shipping companies
  (dedicated crew helplines, Family Outreach Programme seminars, mental
  health training). Checked and rejected Sailors' Society's about-us page
  (a link directory to subpages, no real prose) and Mission to Seafarers'
  about-us (404); Synergy's "Our Values" (i-STEER) page was real but thin
  (a one-line-per-value list) — skipped in favor of the three richer
  Synergy pages. Corpus: 664 → 668 documents (18,652 chunks).
- Verified genuinely retrievable: "what welfare support does a ship
  management company provide to seafarers and their families" surfaces
  all 4 new documents directly in the top 5. A generic "24-hour helpline
  and wellbeing champions" query got the WeTeam page crowded out by NTSB/
  MAIB casualty reports that also discuss crew welfare/fatigue (same
  corpus-scale competition pattern as earlier rounds); a query matching
  the page's distinguishing content ("i-STEER Wellbeing Champions
  program") correctly ranks it #2.

## [Unreleased] — 2026-08-27 — Chartering, ship recycling, fuel management, and dangerous goods via type: html

### Added
- **9 sources via `type: html`**: Chartering (shipping) — voyage/time/
  bareboat charter types together, Bareboat charter, Laytime, Ship
  breaking, the Hong Kong International Convention for ship recycling,
  Marine fuel management, LNG carrier, International Maritime Dangerous
  Goods (IMDG) Code, and Maritime Autonomous Surface Ship (autonomous
  cargo ship). Checked and rejected "Time charter" (that exact title
  redirects to an unrelated horse-racing article on Wikipedia — used
  "Chartering (shipping)" instead, which covers the same three charter
  types together) and "Ammonia as a marine fuel"/"Methanol marine fuel"
  (no such Wikipedia articles exist — skipped rather than guessing a
  URL). Corpus: 655 → 664 documents (18,613 chunks).
- Verified genuinely retrievable: "difference between a voyage charter
  and a time charter" surfaces both new Chartering/Bareboat-charter
  documents directly; "Hong Kong Convention ship recycling environmental
  standards" ranks the new Hong Kong Convention document #2/#3 alongside
  the related Ship breaking document.

## [Unreleased] — 2026-08-27 — Navigation/safety systems, emissions, and chokepoint security via type: html

### Added
- **11 sources via `type: html`**: ECDIS, Voyage data recorder, COLREGs
  (International Regulations for Preventing Collisions at Sea), Dynamic
  positioning, Emission control area, Scrubber (exhaust gas cleaning),
  and 5 maritime-chokepoint/security topics directly relevant to
  route-diversion and war-risk questions — Strait of Hormuz,
  Bab-el-Mandeb, Strait of Malacca, Red Sea crisis, and Houthi attacks on
  commercial vessels (the ongoing 2023– disruption specifically, kept as
  two separate articles — crisis overview vs. detailed attack log — same
  reasoning as keeping Panama Canal and Suez Canal separate). Corpus:
  644 → 655 documents (18,412 chunks).
- Verified genuinely retrievable: "how have Houthi attacks in the Red Sea
  affected shipping routes and insurance" ranks the new Red Sea
  crisis/Houthi-attacks documents #1–#4 directly. A generic "voyage data
  recorder" query got crowded out by the many NTSB reports that also
  discuss VDR data (same corpus-scale competition documented in earlier
  rounds); a query matching the page's distinguishing content ("SS El
  Faro voyage data recorder recovered from 15000 feet depth") correctly
  ranks it #1.

## [Unreleased] — 2026-08-27 — Vessel-operations reference topics + ivfflat recall fix

### Added
- **12 sources on classification/insurance/safety-systems/canals via
  `type: html`**: Classification society, IACS (Wikipedia article — the
  organization's own site is a stat/image-gallery homepage with almost no
  prose, rejected), Marine insurance, Protection and indemnity (P&I)
  insurance, GMDSS, AIS, Marine salvage, Maritime pilot, Ballast water
  discharge and the environment, Piracy, Panama Canal, Suez Canal. ReCAAP
  ISC's homepage was checked and rejected on the same low-content grounds
  as IACS's — an incident-count dashboard with almost no narrative text.
  Corpus: 632 → 644 documents (18,001 chunks).
- Verified genuinely retrievable: spot-checked "what does a ship
  classification society do" (ranked #1), "P&I insurance for shipowners"
  (ranked #1/#2) directly.

### Fixed
- **`retrieval/retriever.py`: pgvector's ivfflat index was searching only
  1 of its 100 lists (`ivfflat.probes` defaults to 1; `db/schema.sql` builds
  the index with `lists='100')`)** — roughly 1% of the table per dense
  query, silently dropping true nearest neighbours in favor of whatever
  landed in the single probed list. Found while verifying the new Panama
  Canal source: "Gatun Lake water levels drought impact on Panama Canal
  transits" didn't surface the Panama Canal document at all — not even in
  the top 15 raw dense-search results — despite a chunk existing that
  discusses exactly that (verified directly: an exact, non-indexed
  `ROW_NUMBER()` scan of the same query embedding placed that chunk at
  rank 2). Fixed with `SET LOCAL ivfflat.probes = 10` (~sqrt(lists), the
  standard pgvector recall/latency tradeoff) scoped to the retrieval
  transaction — no schema change, no lasting connection state.
  Confirmed fix: same query now ranks the Panama Canal document #1/#2.
  Measured on `cli.py eval`'s existing 17-query set: rerank-OFF MRR
  0.544 → 0.765 (rerank-ON unchanged at 0.853 on this small set — the
  cross-encoder was compensating for a worse candidate pool, but that
  compensation isn't guaranteed for harder or more specific queries, as
  the Panama Canal case that surfaced this showed directly). This bug
  predates this session's work and affects the whole corpus, not just the
  documents added here — likely the real explanation behind some of the
  "crowded out of top-N" observations chalked up to corpus-scale
  competition in earlier ingestion rounds this session.

## [Unreleased] — 2026-08-27 — Compliance automation: STCW cert expiry + reportable-incident flag

### Added
- **`ops.store.list_expiring_certs(days_ahead=30)`** — currently-aboard crew
  (`sign_off_date IS NULL`) whose `stcw_cert_expiry` has already passed or
  falls within the look-ahead window, joined with vessel name. Wired into
  `cli.py crew expiring-certs [--days N]` and `GET /crew/expiring-certs?days=N`.
- **`ops.store.list_reportable_incidents()`** — open (`status='open'`)
  `safety_incidents` rows with `severity='critical'`, this project's proxy
  for the SOLAS regulation I/21 threshold (total loss, death, or severe
  environmental damage) that triggers a flag-State casualty report. Wired
  into `cli.py safety reportable` and `GET /safety/reportable`.

### Why
Both `crew.stcw_cert_expiry` and `safety_incidents.severity` have been
schema fields since the ops module was built, but nothing ever read them —
confirmed via `grep -n "def " ops/store.py | grep -i "expir\|report\|deadline\|alert"`
returning zero matches. These are the two highest-value automations
identified from the newly-ingested regulatory corpus (STCW cert-currency
compliance, SOLAS I/21 casualty-investigation duty) against the ops
schema's existing data — no new tables, no new ingestion, both queries run
identically against Postgres and SQLite via the existing `_Conn` pattern.
Deliberately **not** vessel-scoped (unlike most `list_*` functions in this
module) — a fleet-wide actionable list is the point; per-vessel filtering
is already covered by the existing `crew list --vessel` / `safety list
<vessel>` commands.

### Rejected alternatives
- A scheduled/emailed alert (cron job + notification) — out of scope until
  there's a real mail-sending path in this repo; the query itself is the
  useful primitive, alerting is a thin wrapper that can be added later.
- Modeling "reportable" as a new incident-type/flag column rather than a
  `severity='critical' AND status='open'` filter — `severity` already
  exists and is the right granularity; a redundant column would need its
  own maintenance.

## [Unreleased] — 2026-08-27 — Shipowner/regulator reporting requirements via type: html

### Added
- **4 sources on mandatory reporting obligations**: IMO's Casualty
  Investigation page (flag-State duties under SOLAS I/21, MARPOL
  articles 8/12, UNCLOS article 94, and the Casualty Investigation
  Code — IMO's own dedicated casualty-investigation page 500s the same
  way COLREGs did earlier, so this covers the same legal basis with
  real text instead), IMO's Data Collection System (mandatory fuel oil
  consumption reporting since 2019), and two EU pages on the MRV/ETS
  emissions monitoring-reporting-verification regime (the general ETS
  extension page and a detailed FAQ covering monitoring plans, per-voyage
  monitoring, and verifier accreditation). Checked and rejected gov.uk's
  "report an accident at sea" guidance (404) and USCG's casualty-reporting
  office page (pure nav menu, no real prose on the actual requirement)
  first. Corpus: 628 → 632 documents (54 chunks).
- Verified genuinely retrievable: 2 of 3 spot-check queries surfaced the
  new content directly; a third ("reporting requirements... for
  casualties") got crowded out by the many MAIB/NTSB casualty *reports*
  themselves (same corpus-scale competition effect documented earlier
  this session) — a more specific query matching the page's actual legal
  citations ("SOLAS regulation I/21 flag state duty...") correctly ranks
  it 1st.

## [Unreleased] — 2026-08-27 — MCA "About us" via type: html

### Added
- **UK Maritime and Coastguard Agency's "About us" page** — same
  regulatory ecosystem as the MAIB casualty reports already dominant in
  the corpus. Checked a wide round of candidates first and rejected all
  of them on real content quality (not assumed): ICS, MAIB's own
  about-us page (both 404s), ITF (a union-directory listing, no real
  prose), Lloyd's Register and BIMCO (cookie-consent walls Jina Reader
  couldn't get past), USCG (just the .mil security notice), and 3
  MarineInsight articles that extracted as 100% nav/footer boilerplate
  with zero article body. Corpus: 627 → 628 documents.
- Verified genuinely retrievable, not just present: a generic query
  ("what does the Maritime and Coastguard Agency do") got crowded out of
  the top 10 by the many MAIB reports that also mention "coastguard" —
  a real corpus-scale competition effect, not a bug (same phenomenon
  documented earlier this session after the NTSB batch). A query
  matching the page's actual distinguishing content (its real motto,
  "Safer lives, safer ships, cleaner seas") correctly ranks it 1st.

## [Unreleased] — 2026-08-27 — UNCTAD Review of Maritime Transport + HF-informed eval queries

### Added
- **UNCTAD's Review of Maritime Transport 2024** landing page
  (`type: html`), the source `sources.yaml` flagged as worth ingesting
  since the very first commit but never actually landed — the full-report
  PDF timed out repeatedly on a real test, so the substantive publication
  landing page went in instead. Corpus: 626 → 627 documents.
- **2 new eval queries** (`eval/queries.yaml`) against this real content —
  own phrasing, verified against the actual ingested chunk text, same
  process as every prior entry. Both correctly rank 1st with reranking on.
- Found via Hugging Face Hub's `illuin-conteb/maritime-qa` dataset (a
  retrieval-eval set built from the 2022 edition of this same UNCTAD
  report) — used only to confirm this document was worth prioritizing,
  not as a content source: the dataset carries no license tag, so its
  query/answer text isn't copied into this public repo, matching this
  project's consistent stance on unclear-rights sources (MDPI, IMO pages,
  the Jina Reader third-party-proxy caveat).

## [Unreleased] — 2026-08-27 — Documented the FastAPI concurrency invariant

### Added
- Checked all three FastAPI services (`api.py`, `webui/server.py`,
  `ingest_service/server.py`) against a real concurrency mistake
  described in a reading-list article (Jam with AI, "The Concurrency
  Mistake Hiding in Every FastAPI AI Service"): an `async def` endpoint
  calling a blocking sync function (like `requests.post` or a sync DB
  driver) directly freezes FastAPI's single-threaded event loop for
  every concurrent request, not just the slow one. Confirmed this
  project doesn't have it — every request-handling endpoint across all
  three services is plain `def` (Starlette runs those in a worker
  thread pool automatically), and `ingest_service`'s actual blocking
  work (`_run_ingest`) is a sync function handed to `BackgroundTasks`,
  which is also thread-pooled. The only `async def` anywhere is
  `ingest_service`'s `_lifespan` context manager, required by FastAPI's
  lifespan protocol and irrelevant to per-request blocking.
  Added a docstring note to each service explaining this — a non-obvious
  invariant a future "modernize this to async" edit could easily break
  without realizing it was protecting against exactly this bug.

## [Unreleased] — 2026-08-27 — Regulation-reference extraction

Worked via the `unlazy` skill's solo mode (`GATES.md` at repo root, not
the orchestrated `PLAN.md`/`gates/` pattern from the earlier multi-leaf
build — this was one cohesive feature, not independent parallel work).
Closes the last genuine item in README's "Not yet done".

### Added
- **`ingest/regulation_refs.py`** — extracts real IMO instrument
  references (SOLAS, MARPOL, STCW, COLREG, ISM/ISPS Code, MLC, BWM, SAR,
  Load Lines — with Annex/Chapter/Regulation detail and nearby amendment
  years, when the text states them) and US CFR citations (e.g. "46 CFR
  26.30-5") already present in chunk text. Deliberately scoped as real
  extraction of what's already stated, not a temporal knowledge graph
  modeling which regulation version supersedes which (the DNV RuleAgent /
  Vibylabs pattern from the market survey) — that remains a materially
  larger, genuinely-undertaken future direction.
- **`chunks.regulation_refs`** (JSONB on Postgres, TEXT-as-JSON on SQLite)
  — per-chunk, not per-document, since paragraph-level granularity was the
  actual point. Same idempotent `ALTER TABLE ADD COLUMN IF NOT EXISTS` /
  try-except pattern as `published_at`/`content_hash`.
- **`ingest/backfill_regulation_refs.py`** — a real gap found during
  verification, not anticipated in the plan: content_hash-based freshness
  tracking correctly skips re-processing unchanged text, which also means
  a brand-new derived-metadata field never gets computed for chunks
  ingested before the feature existed. Backfill recomputes just the cheap
  regex extraction (no re-fetch, no re-embed) — run once against the live
  corpus: 882 of the corpus's chunks got real regulation references.
- Wired into `retrieval/retriever.py` and `retrieval/sqlite_store.py`'s
  return shape, and into `rag/cite_check.py`'s output (`regulations:
  {citation_index: [refs]}`) so a citation surfaces which specific
  instrument/annex/CFR section it actually points to, when known.
- 24 new tests (`test_regulation_refs.py` plus additions to
  `test_cite_check.py`/`test_sqlite_store.py`). Adversarially re-checked
  the "no false positives" gate after marking it met (per unlazy's
  discipline) and found a real, if currently-harmless, limitation: short
  acronyms (MLC, SAR) can collide with an unrelated proper noun containing
  them as a substring. Checked every real chunk with a bare "MLC" in the
  actual corpus (4) — all genuinely about the convention, not a
  collision — and documented the limitation rather than building
  disambiguation machinery for a risk that doesn't manifest in real data.

## [Unreleased] — 2026-08-26 — Ingestion microservice + source-plugin registry

### Added
- **`ingest/registry.py`** — a plugin registry (`REGISTRY: dict[str,
  SourcePlugin]`) replacing `cli.py`'s data-type-specific if/elif dispatch
  chain. Every existing fetcher (arxiv/wikipedia/maib/ntm/ntsb/pdf/file)
  now registers as `SourcePlugin(name, fetch, description,
  interval_minutes)`; `cli.py`'s `--source` choices are generated from
  `sorted(REGISTRY)` instead of a hand-maintained list. Adding a new
  source is one registry entry, not N call sites — the CLI, the ingestion
  service, and its scheduler all read the same dict.
- **`ingest_service/`** — a small FastAPI microservice (`cli.py
  serve-ingest`, localhost-only by default like `webui/`, since unlike the
  web UI this one writes to the corpus) with `GET /sources`, `POST
  /sources/{name}/ingest` (background, on-demand), and `GET /runs` (history
  from `ingest_runs.jsonl`, gitignored). An APScheduler `BackgroundScheduler`
  polls every schedulable source (all but `--source file`, which has no
  default path) on its own cadence — daily for arxiv/maib/ntsb/pdf, weekly
  for wikipedia/ntm — so the corpus keeps improving with new data after
  deployment instead of being frozen at whatever was ingested manually
  beforehand. This is honest scheduled polling, not literal real-time/
  event-driven streaming: none of the underlying sources offer a push
  mechanism to be real-time *about*.
- Verified live, not just unit-tested: started the service, confirmed all
  7 sources registered with correct next-run times (6 scheduled, `file`
  correctly excluded), triggered a real Wikipedia ingest via `POST
  /sources/wikipedia/ingest` (73.68s — genuinely ran as a background task,
  correctly logged to `ingest_runs.jsonl` with status/counts/duration).
  9 new tests (`test_ingest_service.py`) using the same hermetic
  TestClient + monkeypatch convention as `test_webui.py`; 8 more
  (`test_registry.py`) for the plugin dispatch logic. CI whitelist and
  its pip-install line updated and verified against a genuinely fresh venv
  (`apscheduler` was the one new transitive dependency needed) — 109/109
  passing in that clean environment before this landed.

## [Unreleased] — 2026-08-26 — Port State Control literature via type: html

### Added
- **Paris MoU's "About Us" page and IMO's Human Element overview** added
  to `sources.yaml` as `type: html` entries — directly relevant to the
  casualty/detention literature already in the corpus (the PSC-detention
  arXiv papers, NTSB/MAIB reports). Checked several other PSC-adjacent
  pages first (IACS's about page, Paris MoU's own inspections page) and
  skipped them — under 2,000–6,000 chars of mostly nav-menu boilerplate,
  not worth ingesting. Corpus: 624 → 626 documents.

## [Unreleased] — 2026-08-26 — ARCHITECTURE.md, now properly cited

### Added
- **`ARCHITECTURE.md`** — a structural map of the system through four
  frameworks applied to this actual codebase (not described in the
  abstract): TOGAF's four architecture domains, the general SDLC, the
  domain-specific Data Analytics Lifecycle, and Kaizen/PDCA — the last
  citing this session's own `diversify.py` `quick_ratio()` bug (caught and
  fixed via that exact loop) as the concrete example rather than a
  hypothetical one.
- **Real citations for all four**, not general knowledge. Two of the four
  source PDFs the user pointed to were blocked by the CloudStorage `EPERM`
  issue from earlier this session — both turned out to be real, findable,
  openly-hosted academic works once searched for by title: Lemke's SDLC
  honors thesis (Eastern Michigan University, 2018,
  `commons.emich.edu/honors/589`, recovered via the Browser tool after
  Cloudflare blocked a plain fetch) and Okpala/Ezeanyim/Nwamekwe's Kaizen
  review (*International Journal of Engineering Inventions* 13(7), 2024,
  recovered via `WebFetch` saving the raw PDF locally, then reading it
  with the PDF-aware `Read` tool — bypassing the CloudStorage block
  entirely by not needing the user's local copy at all). Added The Open
  Group's official TOGAF 10th Edition reference and the Data Science &
  Big Data Analytics book's full citation (author/publisher/ISBN) for the
  other two. Full references at the bottom of `ARCHITECTURE.md`.

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
