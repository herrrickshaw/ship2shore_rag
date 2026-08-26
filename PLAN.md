# Plan: close ship2shore_rag's remaining "Not yet done" gaps

Depth: tree 4   Mode: orchestrated
Budget note: four disjoint subsystem-level leaves (freshness tracking,
citation verification, NTSB crawler investigation, minimal web UI) — each
genuinely exceeds one focused sitting; a competent single pass through all
four sequentially would be most of a working day. Dispatched as fresh
subagents per leaf via the Agent tool (ruflo's swarm_init/agent_spawn is
configured but its MCP server is unreachable — `claude mcp list` shows both
`ruflo` and its `claude-flow` alias failing to connect with a timeout,
consistent with the standing memory note that ruflo's tooling is a dead
end). The Agent tool is Claude Code's actual working equivalent for
per-leaf fresh-context dispatch, which is the mechanism orchestrated mode
actually needs — not a specific vendor's swarm API.

## Contract

Decided BEFORE fan-out. Everything a leaf could get wrong about its neighbors:

- **File ownership (no two leaves touch the same file):**
  - 1.1 (freshness): `db/schema.sql`, `retrieval/sqlite_store.py` (schema
    section only), `ingest/ingest.py`, new `ingest/freshness.py`, new
    `tests/test_freshness.py`
  - 1.2 (citations): new `rag/cite_check.py`, new `tests/test_cite_check.py`
  - 1.3 (NTSB crawler): `ingest/sources.py` (new `fetch_ntsb` function,
    additive only — do not touch `fetch_arxiv`/`fetch_maib`/`fetch_pdf`)
  - 1.4 (web UI): new `webui/index.html`, new `webui/server.py`, new
    `tests/test_webui.py`
- **Driver-owned integration (none of the leaves touch these — merge
  conflicts and shared-file races belong to the branch gate, not a leaf):**
  `cli.py`, `.github/workflows/quality-gates.yml`, `README.md`,
  `CHANGELOG.md`, `requirements*.txt`
- **Naming/conventions:** match existing style exactly — lazy `@lru_cache`
  singletons for any loaded model (see `ingest/embed.py`), `STORAGE_BACKEND`
  dispatch pattern for anything touching both Postgres and SQLite (see
  `retrieval/retriever.py`), no comments explaining WHAT code does, only
  non-obvious WHY, defensive `try/except` around anything optional so a
  failure there can't break the core path (see `retrieval/query_log.py`).
- **Data ownership:** 1.1's `content_hash` column and 1.2/1.4's new modules
  do not share any database table modification — only 1.1 touches schema.
- **NTSB leaf (1.3) explicitly may end in a genuine ABANDON** if, after a
  real investigation (not an assumption), no stable public endpoint exists.
  A well-evidenced ABANDON is a valid, honest leaf outcome per unlazy's own
  rules — it is not a failure to avoid at the cost of fabricating a fetcher
  against an endpoint that doesn't really work.

## Tree

- 1 close remaining "Not yet done" gaps .... gates/node-1.md (integration, driver-owned)
  - 1.1 incremental re-crawl / freshness tracking ... gates/leaf-1.1.md
  - 1.2 chunk-level citation verification ........... gates/leaf-1.2.md
  - 1.3 automated NTSB crawler (investigate first) ... gates/leaf-1.3.md
  - 1.4 minimal web UI ............................... gates/leaf-1.4.md

## Status log

Append-only. One line per event: leaf started, leaf verified, gate abandoned.

- plan written, contract fixed, ruflo confirmed unreachable (mcp timeout), Agent tool substituted
- leaves 1.1, 1.2, 1.3, 1.4 dispatched in parallel via Agent tool (file-disjoint per contract)
