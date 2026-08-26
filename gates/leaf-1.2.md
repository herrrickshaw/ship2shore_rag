# Gates: chunk-level citation verification

Scope: a standalone `rag/cite_check.py` that checks a generated answer's
inline `[n]` citation markers against the passages actually retrieved for
it — catching both out-of-range citations (hallucinated numbering) and
citations to a passage the answer's claim doesn't actually resemble
(weak grounding), using no LLM call (lexical/word-overlap only, consistent
with eval/evaluate.py's existing no-LLM-judge philosophy this session).

- [x] G1: rag/cite_check.py exists and is importable
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && .venv/bin/python3 -c "from rag.cite_check import check_citations; print('ok')"
  EXPECT: ok
  EVIDENCE: Ran the check command verbatim -> printed "ok" (no error). File created at rag/cite_check.py, `check_citations(answer, passages)` importable.

- [x] G2: correctly flags an out-of-range citation (answer cites [5], only 3 passages given) as invalid
  CHECK: (unit test in tests/test_cite_check.py, run per G7)
  EXPECT: pending
  EVIDENCE: test_out_of_range_citation_flagged in tests/test_cite_check.py — answer cites [1] then [5] against a 3-passage list; asserted result["valid"] is False and result["out_of_range"] == [5]. `pytest -q tests/test_cite_check.py::test_out_of_range_citation_flagged` -> "1 passed".

- [x] G3: does NOT flag a well-formed answer whose citations are all in range as invalid (no false positive)
  CHECK: (unit test)
  EXPECT: pending
  EVIDENCE: test_in_range_citations_not_flagged_as_out_of_range — answer cites [1],[2],[3] against the same 3-passage list with each sentence matching its passage's real content; asserted out_of_range == [], valid is True, citation_count == 3. `pytest -q tests/test_cite_check.py::test_in_range_citations_not_flagged_as_out_of_range` -> "1 passed".

- [x] G4: flags a sentence citing a passage with near-zero lexical overlap with that sentence as weakly grounded
  CHECK: (unit test with deliberately mismatched content, e.g. a sentence about "engine fires" citing a passage about "bills of lading")
  EXPECT: pending
  EVIDENCE: test_weak_grounding_flagged_for_mismatched_content — "The engine caught fire during the voyage [3]." cited against the bill-of-lading passage. Measured overlap_ratio = 0.0 (verified directly via `_jaccard(_tokenize(sentence), _tokenize(passage))` in a standalone script), well below WEAK_GROUNDING_THRESHOLD=0.08. result["valid"] is False, weak_grounding has exactly 1 entry with citation_index 3. `pytest -q tests/test_cite_check.py::test_weak_grounding_flagged_for_mismatched_content` -> "1 passed".

- [x] G5: does NOT flag a sentence that closely paraphrases its cited passage as weakly grounded (no false positive on genuine grounding)
  CHECK: (unit test)
  EXPECT: pending
  EVIDENCE: test_close_paraphrase_not_flagged_as_weak_grounding — "The ship's main engine caught fire due to an electrical short circuit in the generator room [1]." paraphrases passage [1] ("The vessel's main engine caught fire after an electrical short circuit in the generator room..."). Measured actual jaccard overlap = 0.5556 (verified directly, well above the 0.08 threshold — comfortable margin, not a coin-flip). weak_grounding == [], valid is True. `pytest -q tests/test_cite_check.py::test_close_paraphrase_not_flagged_as_weak_grounding` -> "1 passed".

- [x] G6: runs against a REAL result from rag.pipeline.ask() against the live corpus (not just synthetic fixtures) — report what it finds, even if generation is unavailable (no ANTHROPIC_API_KEY) and the check therefore has to run on a hand-built answer string that cites the real retrieved passages instead
  CHECK: (script provided in leaf brief; must show real passage content/titles from the actual Postgres corpus, not fixture data)
  EXPECT: pending
  EVIDENCE: Confirmed config.ANTHROPIC_API_KEY is empty (.env has ANTHROPIC_API_KEY= with no value) -> `ask()` on the live corpus returned answer=None as expected (asserted in-script). Called `ask("What causes engine room fires on cargo vessels?", top_k=3)` against the live Postgres corpus (131 docs); it returned 3 real passages, 2 from NTSB report "Contact of Containership Dali with the Francis Scott Key Bridge" (https://www.ntsb.gov/investigations/AccidentReports/Reports/MIR2540.pdf) and 1 from "International Maritime Organization" (Wikipedia) — real titles/URLs/content, not fixtures. Hand-built a 4-sentence answer citing [1]-[4] using real phrases lifted from those passages' actual content, then ran check_citations against the real passages list. Result (captured verbatim):
    {
      "valid": false,
      "out_of_range": [4],
      "weak_grounding": [
        {"sentence": "Investigators also found electrical arcing damage on wire ferrules consistent with a degraded connection [2].", "citation_index": 2, "overlap_ratio": 0.0451},
        {"sentence": "The IMO adopted new greenhouse gas emissions reporting requirements for cargo vessels in 2018 [3].", "citation_index": 3, "overlap_ratio": 0.0508}
      ],
      "citation_count": 4
    }
  Findings: [4] correctly caught as out-of-range (only 3 real passages retrieved). [1] correctly passed (sentence closely tracked passage 1's real content about the loose signal wire/low-voltage bus). [2] and [3] were flagged weak — on inspection this is a legitimate finding, not a checker bug: passage 2's real content is mostly a figure/table-of-contents listing ("Figure 62... Figure 63...") rather than prose, so genuine word overlap with any claim sentence is naturally low even on-topic; passage 3's real content says the IMO faced criticism for "relative inaction" on GHG emissions, which my sentence ("adopted new... requirements in 2018") actually contradicts rather than restates — i.e. the checker caught a genuinely unsupported/fabricated-sounding claim against the real corpus text, which is exactly the failure mode it exists to catch.

- [x] G7: tests/test_cite_check.py exists and passes standalone
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && .venv/bin/python3 -m pytest -q tests/test_cite_check.py
  EXPECT: passed
  EVIDENCE: `pytest -q tests/test_cite_check.py` -> "........  [100%]  8 passed in 0.02s" (all 8 tests: out-of-range, in-range no-false-positive, weak-grounding mismatch, paraphrase no-false-positive, citation-after-period attachment, no-citations valid, empty-answer valid, multi-citation-in-one-sentence).

- [x] G8: full existing CI-whitelisted test suite still passes (no regression — this leaf should not have touched any existing file)
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && .venv/bin/python3 -m pytest -q tests/test_chunk.py tests/test_sources.py tests/test_sqlite_store.py tests/test_loaders.py tests/test_export.py tests/test_ops_auth.py tests/test_ops_store.py tests/test_api.py
  EXPECT: passed
  EVIDENCE: `pytest -q tests/test_chunk.py tests/test_sources.py tests/test_sqlite_store.py tests/test_loaders.py tests/test_export.py tests/test_ops_auth.py tests/test_ops_store.py tests/test_api.py` -> "..............................................  [100%]  46 passed, 1 warning in 1.03s" (warning is a pre-existing httpx/starlette deprecation notice, unrelated to this leaf's changes). git status confirms only rag/cite_check.py (new) and tests/test_cite_check.py (new) were touched.

<!--
Leaf brief context: ask() in rag/pipeline.py returns {"answer": str|None,
"passages": [{"content","title","url","source","score",...}]}. Citation
markers in the answer look like "[1]", "[2]" per rag/pipeline.py's
SYSTEM_PROMPT ("Cite sources inline as [1], [2], etc."), 1-indexed against
the passages list in order. Suggested function shape:
check_citations(answer: str, passages: list[dict]) -> dict returning at
least {"valid": bool, "out_of_range": [...ints...], "weak_grounding":
[...{sentence, citation_index, overlap_ratio}...], "citation_count": int}.
Use difflib or a plain word-set Jaccard for the overlap score (retrieval/
diversify.py in this repo uses difflib.SequenceMatcher.ratio() for a
similar "how similar is this text" need — consistent precedent, though the
grounding question here is "does this claim draw from this passage" which
a word-overlap Jaccard on lowercased tokens is a reasonable, simple
proxy for). Do not add an LLM-judge path — that's explicitly out of scope,
matching this session's already-stated eval philosophy (see eval/
evaluate.py's docstring).
-->
