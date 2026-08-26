import os
from pathlib import Path

ROOT = Path(__file__).parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(ROOT / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/ship2shore")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DIM = 384  # matches all-MiniLM-L6-v2
RERANKER_MODEL = os.environ.get("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
# Character count, not tokens: no tokenizer dependency exists in this repo,
# and one isn't worth adding just for a budget guard. ~80k chars is a rough,
# conservative stand-in for Claude's context window minus system prompt/
# question/answer headroom -- generous at today's top_k=5 (a passage is
# ~1-2k chars), the guard exists for when top_k gets raised, not because
# it's binding now.
MAX_CONTEXT_CHARS = int(os.environ.get("MAX_CONTEXT_CHARS", "80000"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# STORAGE_BACKEND selects where retrieval reads from:
#   "postgres" (default) — shore-side: full ingestion + Postgres/pgvector.
#   "sqlite"              — vessel-side: a single portable file, no DB server,
#                            no network. Built via `cli.py export-sqlite` shore-side
#                            and copied aboard (USB / low-bandwidth sync at port).
# See README "Shipboard deployment" for why this split exists.
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "postgres")
SQLITE_PATH = os.environ.get("SQLITE_PATH", str(ROOT / "ship2shore.sqlite3"))

# Operations module (crew/vessel/logs/maintenance) uses the same STORAGE_BACKEND
# switch but its own SQLite file — it's live data written to at sea, not a
# read-only literature snapshot, so keeping it separate from SQLITE_PATH avoids
# conflating "distributed copy" with "source of truth being written to".
OPS_SQLITE_PATH = os.environ.get("OPS_SQLITE_PATH", str(ROOT / "ship2shore_ops.sqlite3"))
