## Regulation-reference extraction

Citation traceability is source-link + per-citation grounding check
(`rag/cite_check.py`) *plus* per-paragraph regulation references:
`ingest/regulation_refs.py` extracts real IMO instrument mentions (SOLAS,
MARPOL, STCW, COLREG, ISM/ISPS Code, MLC, BWM, SAR, Load Lines — with
Annex/Chapter/Regulation detail and nearby amendment years, when present)
and US CFR citations already present in chunk text, stored per-chunk
(`chunks.regulation_refs`, both backends) and surfaced in retrieval results
and `check_citations()`'s output. Run `python3 -m
ingest.backfill_regulation_refs` after upgrading to compute it for chunks
ingested before this existed — freshness tracking correctly skips
re-processing unchanged text, which also means it won't retroactively add
new derived metadata on its own.

This is real extraction of what's already stated in the text, not a
temporal knowledge graph modeling which version of a regulation supersedes
which (the DNV RuleAgent / Vibylabs pattern from the market survey) — that
remains a materially larger, undertaken future direction, not implemented.
