"""Append-only query log — one JSON line per ask() call.

Nothing in this repo logged a query before this: no way to see what's
actually being asked, what came back, or to build an eval set (see
eval/queries.yaml) from real usage instead of invented queries. Plain
JSONL, gitignored, same convention as this repo's other local-run-output
files (ship2shore.sqlite3, warehouse/*.duckdb) — no new dependency, no
schema change, and a logging failure must never break an answer.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).parent.parent / "query_log.jsonl"


def log_query(
    question: str,
    passages: list[dict],
    top_k: int,
    rerank: bool,
    generated: bool,
    path: Path = LOG_PATH,
) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "top_k": top_k,
        "rerank": rerank,
        "generated": generated,
        "passages": [
            {
                "url": p.get("url"),
                "title": p.get("title"),
                "score": p.get("score"),
                "rerank_score": p.get("rerank_score"),
            }
            for p in passages
        ],
    }
    try:
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # logging must never break an answer
