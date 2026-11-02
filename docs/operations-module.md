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

**Deployed.** Live at `https://ship2shore-ops-api.fly.dev` (Fly.io, `sin`
region, `fly.toml` at repo root), backed by a small unmanaged Fly Postgres
app (`ship2shore-ops-db`, `shared-cpu-1x`, 3GB volume — a few $/month,
chosen over Fly's Managed Postgres at $38+/month as the right scale for this
project, not a production fleet system). `min_machines_running = 0` /
`auto_stop_machines = "stop"` in `fly.toml` means it scales to zero when
idle and wakes on the next request, so leaving it running costs very little.
A public read-only demo frontend for it is live at
[ship2shore-ops-demo.lovable.app](https://ship2shore-ops-demo.lovable.app),
seeded with throwaway demo data (2 vessels, one crew member with an
expiring STCW cert, one critical safety incident, one upcoming drydock).

Redeploying after a code change:

```bash
fly deploy -a ship2shore-ops-api
```

`DATABASE_URL` and `API_KEY` are already set as Fly secrets (`fly secrets
list -a ship2shore-ops-api` to see the names, not the values) — `fly deploy`
picks them up automatically, nothing to re-supply.

**Known deviation from `db/init_db.py`:** this Fly Postgres instance does
not have the `vector` extension available, so `cli.py init-db` fails outright
against it (`CREATE EXTENSION vector` errors before it gets to the ops
tables) — expected, since `vector` only matters for the RAG/literature side
(`db/schema.sql`), which this ops-only deployment doesn't run. The schema
was applied directly instead: `db/ops_schema.sql` executed on its own
against the instance (via `fly proxy 5433:5432 -a ship2shore-ops-db` to
reach it from outside Fly's network), skipping `schema.sql` entirely. If
this project's Postgres and the literature corpus's Postgres are ever meant
to be the same instance, that instance needs the `vector` extension
installed first — they are two separate concerns today (see "Operations
module" above), and this deployment only stood up the ops side.

**Known gap, not yet closed:** `allow_origins` in `api.py` is still `"*"`,
not tightened to the Lovable app's actual origin — fine for a public demo
answering only seeded, throwaway data, but the thing to fix first if this
ever serves real fleet data.

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
