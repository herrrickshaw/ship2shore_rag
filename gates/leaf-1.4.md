# Gates: minimal web UI

Scope: a self-contained single-page UI (vanilla HTML/JS, no build step, no
framework — matching this project's simple/self-hostable ethos) backed by
a small dedicated query server, so a question can be asked and cited
results viewed in a browser instead of only via the CLI. Deliberately
separate from api.py (the ops REST API — a different concern, different
auth model): this is read-only literature Q&A, no API key needed, but
binds to localhost only by default since it's meant for local/vessel use.

- [x] G1: webui/server.py starts and serves webui/index.html at GET /
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && (.venv/bin/python3 -m uvicorn webui.server:app --host 127.0.0.1 --port 8020 & sleep 2 && curl -s http://127.0.0.1:8020/ | head -c 200; kill %1 2>/dev/null)
  EXPECT: html
  EVIDENCE: Started `uvicorn webui.server:app --host 127.0.0.1 --port 8020`; `curl -s http://127.0.0.1:8020/` returned HTTP 200 and body starting `<meta charset="utf-8"><title>ship2shore_rag — Ask</title><style>...` (full index.html content). Verified with a separate `curl -s -o /dev/null -w "%{http_code}"` → `200`.

- [x] G2: POST /ask {"question": "..."} returns real retrieved passages from the live Postgres corpus (not a stub/fixture)
  CHECK: (script provided in leaf brief — start the server, curl POST /ask with a real maritime question, confirm the JSON response contains a passage title known to exist in the corpus, e.g. "Bulk carrier" or an NTSB report title)
  EXPECT: JSON body containing a real corpus passage title
  EVIDENCE: `curl -s -X POST http://127.0.0.1:8020/ask -H "Content-Type: application/json" -d '{"question": "What causes bulk carrier hull failure?", "top_k": 5, "generate": false}'` (config.py default STORAGE_BACKEND=postgres, live DB on :5433) returned 5 passages with real Wikipedia-sourced titles "Bulk carrier" (x2), "Container ship" (x2), "Flag of convenience", each with real content text, url, source="wikipedia", and RRF/rerank scores (e.g. 0.0167, 0.0156...) — not stub data.

- [x] G3: the page's JS actually renders results when driven through a real browser (not just curl) — use the Browser tool to load the page, type a question, submit, and confirm rendered result text via read_page or get_page_text
  EVIDENCE: Used mcp__Claude_Browser__preview_start to load http://127.0.0.1:8020/, unchecked "generate answer" checkbox, clicked into the textarea, typed "What causes bulk carrier hull failure?", clicked Ask, waited, then screenshot showed rendered card "[1] Bulk carrier / wikipedia · score 0.0167" with real passage content beneath it. Confirmed again via get_page_text, whose extracted text includes: "[1] Bulk carrier\nwikipedia · score 0.0167\nA bulk carrier or bulker is a merchant ship specially designed to transport unpackaged bulk cargo..." — genuine DOM content from a live fetch('/ask') round-trip, not a screenshot artifact.

- [x] G4: works with STORAGE_BACKEND=sqlite too (vessel-side, no Postgres needed) — start the server with that env var set against the exported ship2shore.sqlite3 snapshot and confirm /ask still returns real results
  CHECK: (script provided in leaf brief)
  EXPECT: JSON body with real passages from the sqlite snapshot
  EVIDENCE: Started `STORAGE_BACKEND=sqlite SQLITE_PATH=/Users/umashankar/repos/ship2shore_rag/ship2shore.sqlite3 .venv/bin/python3 -m uvicorn webui.server:app --host 127.0.0.1 --port 8022`. `curl -X POST http://127.0.0.1:8022/ask -d '{"question": "bulk carrier hull failure", "top_k": 3, "generate": false}'` → HTTP 200 with 2 real passages (title "Bulk carrier", url https://en.wikipedia.org/wiki/Bulk_carrier, source "wikipedia", real content about "Structural problems... In 1990 alone, 20 bulk carriers sank..."), proving the sqlite/sqlite-vec vessel-side backend path (retrieval/sqlite_store.py) is being exercised end-to-end through my server, not Postgres.
  NOTE (out of scope, not fixed here — outside webui/ file ownership): a literal "?" in the question text (e.g. "What causes bulk carrier hull failure?") makes retrieval/sqlite_store.py's FTS5 MATCH query throw `sqlite3.OperationalError: fts5: syntax error near "?"` — a pre-existing bug in that file, reproduced and confirmed independent of my server code (same crash would occur from any caller of retrieve() against sqlite backend with a "?"-containing query). Flagged via spawn_task for separate follow-up; worked around here by testing with a "?"-free question, which is a legitimate/representative query and fully demonstrates the sqlite backend path is wired correctly.

- [x] G5: no XSS — passage title/content is inserted into the DOM safely (textContent or equivalent, never innerHTML with raw string-interpolated untrusted content)
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && grep -n "innerHTML" webui/index.html || echo "no innerHTML use"
  EXPECT: pending (either no matches, or every match is provably safe — judge by hand and record which)
  EVIDENCE: `grep -n "innerHTML" webui/index.html` → no matches (grep exit 1, no output). All passage rendering in the JS (renderPassage()) builds DOM nodes via document.createElement and assigns server-derived strings (p.title, p.content, p.source, p.published_at, p.score) exclusively via `.textContent`, including the title-with-link case (`link.textContent = ...`). The only place a string is inserted as markup is the static inline `<style>`/skeleton HTML written by me, not user/server data. No innerHTML usage anywhere in the file.

- [x] G6: server binds to 127.0.0.1 by default, not 0.0.0.0 — not exposed on the network without an explicit opt-in flag
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && grep -n "127.0.0.1\|0.0.0.0\|host" webui/server.py
  EXPECT: 127.0.0.1
  EVIDENCE: `grep -n "127.0.0.1\|0.0.0.0\|host" webui/server.py` → line 75: `host = os.environ.get("WEBUI_HOST", "127.0.0.1")`, used at line 77 `uvicorn.run(app, host=host, port=port)`. Default is 127.0.0.1; 0.0.0.0 only appears in a comment describing how to opt in via WEBUI_HOST env var — never as the code default.

- [x] G7: tests/test_webui.py exists and passes standalone (FastAPI TestClient style, matching tests/test_api.py's existing convention — no live server needed for this one)
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && .venv/bin/python3 -m pytest -q tests/test_webui.py
  EXPECT: passed
  EVIDENCE: `4 passed, 1 warning in 0.37s` (warning is pre-existing StarletteDeprecationWarning re: httpx, unrelated to this change, also present in test_api.py's run). Tests use TestClient(server.app) + monkeypatch.setattr(server, "ask", fake_ask) — no live Postgres/sqlite/network needed, matching test_api.py's monkeypatch-the-backend convention.

- [x] G8: full existing CI-whitelisted test suite still passes (no regression — this leaf should not have touched any existing file)
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && .venv/bin/python3 -m pytest -q tests/test_chunk.py tests/test_sources.py tests/test_sqlite_store.py tests/test_loaders.py tests/test_export.py tests/test_ops_auth.py tests/test_ops_store.py tests/test_api.py
  EXPECT: passed
  EVIDENCE: `46 passed, 1 warning in 1.07s`. `git status --porcelain` confirms this leaf only added tests/test_webui.py, webui/index.html, webui/server.py (plus its own gates/leaf-1.4.md edits) — all other modified/untracked files in the working tree (cli.py, db/schema.sql, ingest/ingest.py, retrieval/sqlite_store.py, PLAN.md, ingest/freshness.py, rag/cite_check.py, etc.) are pre-existing/other-leaves' concurrent changes, not touched by this leaf.

<!--
Leaf brief context: rag.pipeline.ask(question, top_k, generate, rerank,
since, source_filter) is the function to wrap — see rag/pipeline.py, fully
built and live this session. tests/test_api.py shows this repo's
established FastAPI TestClient testing convention — follow it for
consistency. api.py shows the existing FastAPI app conventions (Pydantic
request/response models, exception handling) but do NOT import from or
depend on api.py — this is a separate, smaller app on a separate port
(suggest 8020, avoiding the existing ops-api's 8010 from
~/.claude/launch.json). Keep index.html genuinely single-file: inline
<style> and <script>, no external CDN/build dependency, matching how this
project avoids heavy frontend tooling everywhere else.
-->
