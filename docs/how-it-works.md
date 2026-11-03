## How it works

```
ingest/sources.py       -> fetches raw documents (arXiv, Wikipedia, MAIB Atom feed, NTSB CAROL API, PDF URLs)
ingest/loaders.py        -> loads local files instead — PDF, TXT/MD, HTML, DOCX, XLSX, PPTX
ingest/chunk.py            -> splits documents into overlapping word-window chunks
ingest/embed.py              -> embeds chunks locally (sentence-transformers)
ingest/freshness.py           -> content_hash so re-ingesting a changed URL updates it in place
ingest/regulation_refs.py      -> extracts real IMO/CFR regulation references from chunk text
ingest/ingest.py                -> orchestrates fetch -> chunk -> embed -> upsert (postgres or sqlite)
retrieval/retriever.py            -> hybrid retrieval: dense cosine + Postgres full-text, fused via RRF
retrieval/sqlite_store.py          -> same hybrid retrieval against the vessel-side SQLite snapshot
retrieval/rerank.py                  -> cross-encoder scores + sorts the candidate pool (no cut)
retrieval/diversify.py                 -> final top-k cut: per-source cap + near-duplicate skip
retrieval/query_log.py                   -> appends one JSON line per ask() call to query_log.jsonl
rag/pipeline.py                            -> builds a cited prompt from top-k chunks, calls Claude (optional)
rag/cite_check.py                            -> flags out-of-range / weakly-grounded [n] citations
rag/export.py                                  -> renders an answer + sources as a compact HTML/text report
db/schema.sql                                    -> documents + chunks tables, ivfflat cosine + GIN full-text index
ingest/export_sqlite.py                            -> snapshots the Postgres corpus into a portable SQLite file
eval/evaluate.py                                     -> Recall@k / MRR against eval/queries.yaml (cli.py eval)
webui/server.py                                        -> small read-only FastAPI app (cli.py serve)
```

Retrieval fuses two rankings via [Reciprocal Rank
Fusion](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) — the same
pattern used for maritime accident-report retrieval in "Multi-Field Hybrid RAG
for Maritime Accident Root Cause Analysis" (arXiv 2606.13249): dense embedding
similarity finds conceptually related passages, keyword search catches exact
terms (vessel names, regulation numbers, IMO numbers) that embeddings can miss.
RRF's fused order is then rescored by a local cross-encoder
(`cross-encoder/ms-marco-MiniLM-L-6-v2`) over a wider candidate pool — RRF
only knows *where* each side ranked a chunk, not how relevant it actually is
to the query, and a cross-encoder reading (query, passage) pairs jointly is
usually the single biggest relevance gain in a hybrid pipeline. Disable with
`ask --no-rerank` / `ask(..., rerank=False)` to fall back to RRF order as-is.
The final top-k cut then goes through a diversity filter
(`retrieval/diversify.py`): caps results per source document and skips
near-duplicate passages, so a handful of near-identical chunks from one
report can't crowd out everything else. `ask --since YYYY-MM-DD` /
`--source-filter {arxiv,wikipedia,maib,ntm,pdf,file}` narrow retrieval by
publish date or ingestion source (only arxiv/maib carry a real publish
date; a `--since` filter excludes everything else). Retrieval quality is
measurable, not just eyeballed — `cli.py eval` runs Recall@k/MRR from
`eval/queries.yaml` against the real corpus, rerank on vs. off.
