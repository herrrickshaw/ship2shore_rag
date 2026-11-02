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
