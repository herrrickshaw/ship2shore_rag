"""Diversity filter — the final top_k cut, applied after reranking.

Two duplication patterns show up in retrieved results (observed live via
query_log.jsonl: a 3-result query returned 3 chunks from the same NTSB
report): same-document adjacent chunks (structurally obvious — same url,
a byproduct of 220-word chunks with 40-word overlap in ingest/chunk.py) and
cross-document duplication, e.g. two different reports quoting the same
regulation verbatim (no structural signal — needs actual text comparison).
Walking the already-ranked list and skipping what's redundant, rather than
scoring "diversity" as its own thing, keeps the ranking rerank.py already
computed intact wherever nothing needs to be dropped.
"""
from difflib import SequenceMatcher

SIMILARITY_THRESHOLD = 0.85


def _is_near_duplicate(content: str, kept_contents: list[str]) -> bool:
    # .ratio(), not .quick_ratio(): quick_ratio is a character-multiset upper
    # bound, not actual sequence overlap -- on natural-language English text
    # of similar length it runs high for ANY two paragraphs (similar letter
    # frequency), flagging unrelated content as duplicates. Verified live:
    # it dropped a genuinely relevant passage because it "matched" boilerplate
    # letter frequency, not because the text was actually similar. .ratio()
    # is slower (real longest-matching-block comparison) but at pool size
    # ~20 that's still trivial.
    return any(SequenceMatcher(None, content, kept).ratio() >= SIMILARITY_THRESHOLD for kept in kept_contents)


def select(passages: list[dict], top_k: int, max_per_source: int = 2) -> list[dict]:
    """passages must already be ranked best-first (rerank.py's output, or
    RRF order if reranking is off). Walks that order, keeping a passage only
    if its source (url) hasn't hit max_per_source and it isn't a near-
    duplicate of something already kept."""
    kept: list[dict] = []
    kept_contents: list[str] = []
    per_source_count: dict[str, int] = {}

    for p in passages:
        if len(kept) >= top_k:
            break
        url = p.get("url")
        if per_source_count.get(url, 0) >= max_per_source:
            continue
        if _is_near_duplicate(p["content"], kept_contents):
            continue
        kept.append(p)
        kept_contents.append(p["content"])
        per_source_count[url] = per_source_count.get(url, 0) + 1

    return kept
