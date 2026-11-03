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
