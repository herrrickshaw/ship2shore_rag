# Gates: close remaining "Not yet done" gaps (integration)

Scope: children 1.1 (freshness), 1.2 (citation verification), 1.3 (NTSB
crawler), 1.4 (web UI) merged into one working whole, wired into cli.py/CI/
README, committed and pushed.

- [x] N1: every child leaf's gates file is fully checked (no unchecked boxes, no pending evidence — ABANDON lines accepted as resolved)
  CHECK: for f in gates/leaf-1.1.md gates/leaf-1.2.md gates/leaf-1.3.md gates/leaf-1.4.md; do node ~/.claude/skills/unlazy/scripts/gate-check.mjs --status "$f"; done
  EXPECT: ALL MET
  EVIDENCE: ran the CHECK command myself (not trusting self-reports): `leaf-1.1.md: ALL MET (8 met)`, `leaf-1.2.md: ALL MET (8 met)`, `leaf-1.3.md: ALL MET (4 met)`, `leaf-1.4.md: ALL MET (8 met)`. Went further than just re-running CHECK commands for 1.2 (adversarial spot-testing: empty passage lists, duplicate markers, glued citations, zero-padded indices — all handled correctly, no bugs found) and 1.1/1.3 (independently reproduced the core claims from a fresh Python process: 1.1's ingest/mutate/re-ingest cycle on a temp sqlite db, 1.3's fetch_ntsb() live call, both matched the self-reports exactly).

- [x] N2: cli.py wired with new entry points from leaves that shipped code (e.g. `serve` for webui, `ntsb` added to --source choices if 1.3 shipped a fetcher) — no wiring needed for a leaf that only produced a standalone importable module (1.2's cite_check) or that ended in ABANDON (possibly 1.3)
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && .venv/bin/python3 cli.py --help
  EXPECT: `serve` subcommand listed, `ntsb` present in `ingest --source` choices
  EVIDENCE: `cli.py --help` output includes `serve` in the subcommand list; `cli.py ingest --help` shows `--source {arxiv,wikipedia,pdf,maib,ntm,ntsb,file}`; `cli.py ask --help`'s `--source-filter` choices updated to match. `cmd_serve()` added, imports `webui.server.app` and runs uvicorn with the same WEBUI_HOST/WEBUI_PORT env-var defaults webui/server.py's own `__main__` uses.

- [x] N3: CI whitelist (.github/workflows/quality-gates.yml) updated to include every new test file the leaves added
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && grep "test_freshness.py\|test_cite_check.py\|test_webui.py\|test_diversify.py\|test_query_log.py\|test_retriever_filters.py" .github/workflows/quality-gates.yml
  EXPECT: all six present
  EVIDENCE: all six new test files present in the pytest invocation line. Also caught and fixed a real gap while verifying this: three of the new test files transitively import `retrieval/retriever.py`, which needs the `pgvector` package at module-import time (not just `psycopg`, which was already installed in CI) — added `pgvector` to the pip install line. Verified for real, not just by inspection: built a genuinely fresh venv (`python3 -m venv /tmp/ci_sim_venv`), installed exactly the CI pip-install line's package list, ran exactly the CI pytest command against it — `88 passed` in the clean venv, confirming the CI fix is both necessary and sufficient. Sim venv removed after.

- [x] N4: README's "Not yet done" section updated to reflect reality — items that shipped removed from that list (with a one-line pointer to the new capability), items genuinely abandoned stay listed but with the real reason from this session's investigation, not the old assumed one
  EVIDENCE: Removed the shipped items (web UI, freshness tracking, citation verification, NTSB crawler) from "Not yet done"; added a "Web UI" section documenting `cli.py serve`; updated the Sources table and prose to describe `fetch_ntsb()`'s real CAROL-API-based discovery using leaf 1.3's drafted wording verbatim (the leaf drafted it specifically for me to apply, per its file-ownership contract — it doesn't touch README.md itself); updated `ingest/sources.yaml`'s header comment to match; updated the "How it works" module list to include the 6 new files; filled in `.env.example` with the previously-undocumented `RERANKER_MODEL`/`MAX_CONTEXT_CHARS`/`WEBUI_HOST`/`WEBUI_PORT` env vars. Remaining "Not yet done" entries are the two genuinely still-open ones: per-paragraph/regulation-version citation tracking (a documented future direction, not attempted this pass) and `--export` not sending email itself (by design, not a gap).

- [x] N5: full existing CI-whitelisted test suite plus every new test file green together in one run
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && .venv/bin/python3 -m pytest -q tests/
  EXPECT: passed
  EVIDENCE: `88 passed, 1 warning in 1.16s` (warning is the pre-existing unrelated httpx/starlette deprecation notice). 88 = 46 original + 8 test_cite_check + 5 test_freshness + 4 test_webui + 6 test_diversify + 4 test_query_log + 10 test_retriever_filters + 5 test_sqlite_store (1 original + 4 new FTS5-regression parametrized cases) — every number re-counted against the actual pytest output, not stated from memory.

- [x] N6: CHANGELOG.md updated with one entry per leaf outcome (matching this session's established convention: decision + why, not just a diff)
  EVIDENCE: added a combined "Close the remaining 'Not yet done' gaps" entry to CHANGELOG.md covering all four leaves' outcomes (freshness tracking, citation verification, NTSB crawler discovery + the README-was-wrong finding, web UI), plus the earlier separate entry for the lint-tooling/test-coverage/FTS5-fix work done directly by the driver outside the leaf dispatch.

- [x] N7: everything committed and pushed to origin/main
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && git status --short && git log origin/main..HEAD --oneline
  EXPECT: both empty
  EVIDENCE: `git push origin main` -> `52150a7..9ed5764  main -> main`. `git status --short` -> empty. `git log origin/main..HEAD --oneline` -> empty. Two commits this integration: 9390354 (lint tooling + test coverage + FTS5 fix, plus the leaves' code already merged into the working tree at that point) and 9ed5764 (driver-owned wiring: cli.py, CI whitelist, README/sources.yaml/.env.example, CHANGELOG, PLAN.md/gates/ as audit trail).

<!--
Branch gates exist because finished parts do not imply a finished whole.
Do not mark N1 by trusting leaf self-reports: re-run their checks yourself.
-->
