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
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
