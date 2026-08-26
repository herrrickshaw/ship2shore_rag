# Gates: regulation-reference extraction (per-paragraph/regulation-version tracking)

Scope: close the last real item in README's "Not yet done" — citation
traceability is currently source-link + grounding-check only
(`rag/cite_check.py`), with no tracking of *which regulation/version* a
passage actually discusses. Deliver a genuinely scoped version of that:
extract real regulation/instrument references (IMO conventions + annexes/
amendments, US CFR citations) already present in chunk text, store them as
structured per-chunk metadata, and surface them in retrieval output and
citation checking. NOT a full temporal knowledge graph with superseding-
version relationships (the DNV RuleAgent/Vibylabs pattern cited in the
market survey) — that's a materially larger project; this is the honestly-
achievable slice of it: real references, extracted and structured, not
fabricated or aspirational ones.

- [x] G1: ingest/regulation_refs.py exists with extract_refs(text) -> list[dict], each entry shaped {"instrument": str, "detail": str|None, "year": int|None, "raw": str}
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && .venv/bin/python3 -c "from ingest.regulation_refs import extract_refs; r = extract_refs('MARPOL Annex VI covers air pollution; the 1997 Protocol added it.'); print(r)"
  EXPECT: MARPOL
  EVIDENCE: ran verbatim -> `[{'instrument': 'MARPOL', 'detail': 'Annex VI', 'year': 1997, 'raw': 'MARPOL'}]`. Module created with INSTRUMENTS list matched against real corpus content (SOLAS/MARPOL/STCW/COLREGS/ISM/ISPS/MLC/BWM/SAR/Load Lines), Annex/Chapter/Regulation detail matching, nearby-year amendment matching, CFR citation matching.

- [x] G2: correctly extracts a real IMO instrument + annex reference from actual corpus text (not a synthetic fixture)
  CHECK: queried the live Postgres corpus (documents.url LIKE '%MARPOL%') for 3 real ingested chunks, ran extract_refs against each
  EXPECT: real MARPOL/Annex/year references found
  EVIDENCE: first real chunk (containing "Adoption: 1973 (Convention), 1978 (1978 Protocol), 1997 (Protocol - Annex VI)... (MARPOL) is the main international convention...") -> `[{'instrument': 'MARPOL', 'detail': None, 'year': None, ...}, {'instrument': 'MARPOL', 'detail': None, 'year': 1978, ...}, {'instrument': 'MARPOL', 'detail': 'Annex VI', 'year': None, ...}]` -- 3 distinct real MARPOL mentions in that chunk (title repeated in the Reader-fetched markdown's Title:/body), 1978 Protocol and Annex VI are both genuinely present in the same chunk's real text. Other 2 chunks (later in the document, past the adoption/annex summary) correctly returned [] -- no regulation language in those specific chunks, confirmed by inspecting their content.

- [x] G3: correctly extracts a real US CFR citation from actual corpus text (the "46 CFR 26.30-5" NTSB chunk found this session)
  CHECK: queried the live corpus for the exact chunk containing "46 CFR 26.30-5" (found earlier this session while designing this feature), ran extract_refs
  EXPECT: CFR reference found
  EVIDENCE: `[{'instrument': 'CFR', 'detail': '46 CFR 26.30-5', 'year': None, 'raw': '46 CFR 26.30-5'}]` -- exact match against the real regulatory citation in that NTSB report chunk.

- [x] G4: does NOT hallucinate a reference where none exists (no false positive on a chunk with no regulation language)
  CHECK: extract_refs against two genuinely unrelated real-style sentences (a vessel-departure narrative, a bill-of-lading definition)
  EXPECT: []
  EVIDENCE: both calls returned `[]` -- no false positives on plain maritime narrative/definitional text with no actual regulation reference. Adversarially re-checked after initially marking this met (per unlazy's "re-read one passed gate adversarially" step): "search and rescue operation" (not the SAR Convention) and bare "ISM procedures" (no "Code") both correctly returned `[]`. Found one genuine limitation trying harder: a constructed "MLC Trader" (hypothetical vessel name containing the MLC acronym as a substring) DOES false-positive -- short acronyms can collide with unrelated proper nouns. Checked whether this is a live problem, not just theoretical: queried every real chunk in the corpus containing a bare "MLC" (4 total) -- all 4 are genuinely about the Maritime Labour Convention ("non-compliance with the MLC", "MLC 2006", listed alongside SOLAS/MARPOL/STCW), none are a name collision. Documented as a known, currently-harmless limitation in regulation_refs.py's docstring rather than fixed with NER/disambiguation machinery disproportionate to a risk that doesn't manifest in real data.

- [x] G5: chunks.regulation_refs column added on both backends (Postgres JSONB NOT NULL DEFAULT '[]', SQLite TEXT NOT NULL DEFAULT '[]'), following the exact ALTER TABLE ADD COLUMN IF NOT EXISTS (postgres) / try-except ALTER TABLE (sqlite) precedent already used for published_at and content_hash. Placed on chunks, not documents -- the whole point is paragraph-level granularity, which a per-document field can't express.
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && .venv/bin/python3 -c "import psycopg; from config import DATABASE_URL; c=psycopg.connect(DATABASE_URL); print(c.execute(\"SELECT column_name FROM information_schema.columns WHERE table_name='chunks' AND column_name='regulation_refs'\").fetchone())"
  EXPECT: regulation_refs
  EVIDENCE: ran `.venv/bin/python3 -m db.init_db` -> "schema ready". CHECK command returned `('regulation_refs',)`. SQLite side: retrieval/sqlite_store.py's SCHEMA now includes `regulation_refs TEXT NOT NULL DEFAULT '[]'` on chunks, plus a try/except ALTER TABLE guard in create_schema() for pre-existing snapshot files, mirroring the published_at/content_hash pattern exactly.

- [x] G6: ingest/ingest.py computes and stores regulation_refs for each chunk at ingest time (both postgres and sqlite paths)
  CHECK: ingest a throwaway doc with real MARPOL/STCW-style text on each backend, query regulation_refs back
  EXPECT: non-empty, correct refs
  EVIDENCE: Postgres: ingested a doc with "MARPOL Annex VI ... 1997 Protocol" text -> `(0, [{'raw': 'MARPOL', 'year': 1997, 'detail': 'Annex VI', 'instrument': 'MARPOL'}])`, cleaned up after. SQLite (temp file, embed_texts mocked): ingested a doc with "STCW Regulation I/1" text -> `0 [{'instrument': 'STCW', 'detail': 'Regulation I/1', 'year': None, 'raw': 'STCW'}]`. Postgres INSERT required wrapping the value in `psycopg.types.json.Json()` -- a plain Python list/dict raised "cannot adapt type 'dict'" on first attempt, confirmed and fixed before this evidence was recorded, not assumed to work.

- [x] G7: retrieval/retriever.py and retrieval/sqlite_store.py return regulation_refs in the passage dict (same pattern as published_at's addition to both backends' SELECT + return shape)
  CHECK: retrieve('MARPOL Annex VI air pollution regulations', top_k=5) against the live corpus
  EXPECT: regulation_refs present and non-empty on real results
  EVIDENCE: Real gap found and fixed along the way: the first run of this CHECK returned regulation_refs=[] on every result -- content_hash-based freshness tracking (by design) skips re-processing unchanged text, so chunks ingested before this feature existed never got regulation_refs computed. Wrote ingest/backfill_regulation_refs.py (recomputes just the cheap regex extraction, no re-fetch/re-embed) and ran it against the live corpus: "backfilled regulation_refs for 882 chunk(s)". Re-ran the CHECK: 4 of 5 results now show real, correct refs, e.g. `[{'raw': 'MARPOL', 'detail': 'Annex VI', ...}]` on the NTSB MAB1721 report, `[{'instrument': 'SOLAS'...}, {'instrument': 'MARPOL'...}, {'instrument': 'STCW'...}, {'instrument': 'MLC'...}]` on the Port State Control page. The 5th (a specific MARPOL-page chunk) correctly shows [] -- that specific 220-word chunk's content doesn't mention MARPOL/Annex in that paragraph, verified by inspection; other chunks of the same document do have refs (confirmed in G2).

- [x] G8: rag/cite_check.py's output surfaces which regulation(s) a citation actually references, when known
  CHECK: check_citations against a real answer citing real MARPOL/NTSB passages retrieved from the live corpus
  EXPECT: regulations dict populated with real refs for in-range citations whose passage has them
  EVIDENCE: retrieved 3 real passages for "MARPOL Annex VI air pollution regulations", built an answer citing [1] and [2], ran check_citations. `result['regulations']` -> `{1: [{'raw': 'MARPOL', ...}, {'raw': 'MARPOL', 'detail': 'Annex VI', ...}], 2: [{'raw': 'MARPOL', 'detail': 'Annex VI', ...}]}` -- both keyed correctly to their citation index, with the actual regulation_refs from those specific passages, not fabricated.

- [x] G9: existing full test suite (109 tests) still passes; new tests added for regulation_refs.py's extraction logic
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && .venv/bin/python3 -m pytest -q tests/
  EXPECT: passed
  EVIDENCE: `123 passed, 1 warning in 1.16s` -- 109 original + 9 (test_regulation_refs.py) + 3 (new cite_check regulations-field tests) + 2 (new sqlite_store regulation_refs round-trip tests) = 123, matches exactly. ruff clean, black clean (after formatting all touched .py files -- one accidental `black db/schema.sql` attempt correctly errored, since black is a Python formatter and that's SQL; not a real issue, just the wrong file passed to the tool).

- [x] G10: README's "Not yet done" entry updated to reflect what actually shipped (real extraction + structured storage) vs. what's still genuinely out of scope (temporal superseding-version graph) -- honest about the boundary, not overclaiming a full knowledge graph
  EVIDENCE: Added a new "Regulation-reference extraction" section to README.md describing exactly what shipped (real IMO/CFR reference extraction, per-chunk storage, retrieval + cite_check surfacing, the backfill command) and explicitly stating what remains out of scope (temporal knowledge graph modeling regulation version supersession). Removed the old "Not yet done" bullet about this since it's no longer accurate -- the remaining "Not yet done" list now has exactly one genuine item left (--export not sending email, which is by design, not a gap).
