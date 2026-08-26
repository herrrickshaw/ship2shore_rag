"""Minimal read-only literature Q&A web UI — a thin FastAPI wrapper around
rag.pipeline.ask(), serving a single self-contained HTML page.

Deliberately separate from api.py (the ops REST API): that one manages
writes to vessel/crew/logbook/maintenance data and needs the X-API-Key +
X-User IAM model. This one only ever reads the literature corpus (Postgres
shore-side or the exported SQLite snapshot vessel-side, per
config.STORAGE_BACKEND) and answers questions — no credentials involved, so
none are required. Because there's no auth, it must never be reachable from
the network by default: binds to 127.0.0.1 unless WEBUI_HOST is set
explicitly (see __main__ below and README "Web UI" for the opt-in).

Endpoints are plain `def`, not `async def` -- deliberately. ask() ->
retrieve() calls psycopg/sqlite3 (sync) and a sentence-transformers model
(sync, CPU-bound); none of that is awaitable. A plain `def` endpoint runs
in Starlette's worker thread pool automatically, so that blocking work
never freezes the event loop. Making this `async def` without also
awaiting every blocking call inside it would be the exact FastAPI mistake
where one slow request stalls every other concurrent request on the same
process -- don't "modernize" this to async without threading async I/O
all the way through ask()/retrieve() first.
"""

import os
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from rag.pipeline import ask

INDEX_HTML_PATH = Path(__file__).parent / "index.html"

app = FastAPI(title="ship2shore_rag web UI", version="0.1.0")


class AskRequest(BaseModel):
    question: str
    top_k: int = 5
    generate: bool = True
    rerank: bool = True
    since: date | None = None
    source_filter: str | None = None


class Passage(BaseModel):
    content: str
    title: str
    url: str | None = None
    source: str | None = None
    published_at: date | None = None
    score: float


class AskResponse(BaseModel):
    answer: str | None
    passages: list[Passage]


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML_PATH.read_text()


@app.post("/ask", response_model=AskResponse)
def post_ask(body: AskRequest) -> dict:
    return ask(
        body.question,
        top_k=body.top_k,
        generate=body.generate,
        rerank=body.rerank,
        since=body.since,
        source_filter=body.source_filter,
    )


if __name__ == "__main__":
    import uvicorn

    # 127.0.0.1 by default — this server has no auth, so it must not be
    # reachable from the network unless someone explicitly opts in by
    # setting WEBUI_HOST (e.g. to 0.0.0.0 for a deliberate LAN/vessel-network
    # deployment).
    host = os.environ.get("WEBUI_HOST", "127.0.0.1")
    port = int(os.environ.get("WEBUI_PORT", "8020"))
    uvicorn.run(app, host=host, port=port)
