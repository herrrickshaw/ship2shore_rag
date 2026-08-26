"""Ingestion microservice — the piece that lets ship2shore_rag's corpus
keep improving after it's deployed, instead of being frozen at whatever
was ingested manually before launch.

Two things this adds on top of cli.py ingest / ingest/registry.py:

1. **Data-type-generic control plane**: one HTTP interface
   (POST /sources/{name}/ingest) over every registered source, not a
   bespoke code path per source type. Adding a new source means adding one
   entry to ingest/registry.py's REGISTRY — this service, the scheduler,
   and every endpoint below pick it up automatically, nothing here changes.
2. **Continuous, not one-shot**: an APScheduler background scheduler polls
   every source with interval_minutes > 0 on its own cadence (see the
   REGISTRY defaults) so the corpus updates on its own. This is honest
   scheduled polling, not literally real-time/event-driven streaming —
   none of the underlying sources (arXiv's API, MAIB/NTM's feeds, NTSB's
   CAROL endpoint, sources.yaml's curated URLs) offer a push/webhook
   mechanism to be real-time *about*, so periodic polling close to their
   own actual update cadence is the correct, non-fabricated way to get
   "the corpus stays fresh without a human running the CLI."

Deliberately separate from api.py (ops REST, different write surface and
auth model) and webui/server.py (read-only Q&A, no write capability at
all) — this one *does* write to the corpus, which is why it stays
localhost-only by default like webui/server.py, with the same opt-in
pattern (INGEST_SERVICE_HOST) rather than a new auth scheme: this is an
operator tool for a single deployment, not something meant to be exposed
publicly the way api.py's ops API is.

Every request-handling endpoint is plain `def`, not `async def`, and
_run_ingest (the function doing the actual blocking work -- requests HTTP
calls, psycopg/sqlite3) is a plain sync function too, passed to
BackgroundTasks rather than awaited. Both matter for the same reason:
Starlette runs plain-`def` endpoints AND sync callables handed to
BackgroundTasks in its worker thread pool automatically, so none of that
blocking I/O ever freezes the event loop -- the classic FastAPI mistake is
an `async def` endpoint calling something blocking directly on the loop,
which this doesn't do anywhere. Don't add `async`/`await` here without
also making the underlying calls (requests -> httpx.AsyncClient, psycopg
-> AsyncConnection) actually async, or this becomes exactly that mistake.
"""

import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from ingest.ingest import ingest_documents
from ingest.registry import REGISTRY, fetch

RUNS_LOG_PATH = Path(__file__).parent.parent / "ingest_runs.jsonl"

scheduler = BackgroundScheduler()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    for name, plugin in REGISTRY.items():
        if plugin.interval_minutes <= 0 or plugin.needs_path:
            continue  # --source file has no default path to poll; not schedulable
        scheduler.add_job(
            _run_ingest,
            trigger=IntervalTrigger(minutes=plugin.interval_minutes),
            args=[name, "scheduled"],
            id=name,
            replace_existing=True,
        )
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="ship2shore_rag ingestion service", version="0.1.0", lifespan=_lifespan)


class SourceInfo(BaseModel):
    name: str
    description: str
    interval_minutes: int
    scheduled: bool
    next_run: str | None = None


class TriggerResponse(BaseModel):
    status: str
    source: str


class RunRecord(BaseModel):
    timestamp: str
    source: str
    trigger: str
    status: str
    fetched: int | None = None
    ingested: int | None = None
    error: str | None = None
    duration_seconds: float | None = None


def _run_ingest(source: str, trigger: str) -> None:
    """The one function both the scheduler and the manual-trigger endpoint
    call — same code path either way, so a scheduled run and a POST
    /sources/{name}/ingest run are provably identical in behavior, not two
    implementations that can drift apart."""
    started = time.monotonic()
    record: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "trigger": trigger,
    }
    try:
        docs = fetch(source)
        count = ingest_documents(docs)
        record.update(status="success", fetched=len(docs), ingested=count)
    except Exception as e:  # a bad source must not crash the scheduler thread
        record.update(status="error", error=f"{type(e).__name__}: {e}")
    record["duration_seconds"] = round(time.monotonic() - started, 2)
    try:
        with open(RUNS_LOG_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass  # logging must never break ingestion, same convention as retrieval/query_log.py


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "scheduler_running": scheduler.running}


@app.get("/sources", response_model=list[SourceInfo])
def list_sources() -> list[SourceInfo]:
    out = []
    for name, plugin in REGISTRY.items():
        job = scheduler.get_job(name)
        out.append(
            SourceInfo(
                name=name,
                description=plugin.description,
                interval_minutes=plugin.interval_minutes,
                scheduled=job is not None,
                next_run=job.next_run_time.isoformat() if job and job.next_run_time else None,
            )
        )
    return out


@app.post("/sources/{name}/ingest", response_model=TriggerResponse)
def trigger_ingest(name: str, background_tasks: BackgroundTasks) -> TriggerResponse:
    if name not in REGISTRY:
        raise HTTPException(status_code=404, detail=f"unknown source: {name!r}")
    background_tasks.add_task(_run_ingest, name, "manual")
    return TriggerResponse(status="started", source=name)


@app.get("/runs", response_model=list[RunRecord])
def list_runs(limit: int = 20) -> list[RunRecord]:
    if not RUNS_LOG_PATH.exists():
        return []
    lines = RUNS_LOG_PATH.read_text().splitlines()
    return [RunRecord(**json.loads(line)) for line in lines[-limit:][::-1]]


if __name__ == "__main__":
    import os

    import uvicorn

    host = os.environ.get("INGEST_SERVICE_HOST", "127.0.0.1")
    port = int(os.environ.get("INGEST_SERVICE_PORT", "8030"))
    uvicorn.run(app, host=host, port=port)
