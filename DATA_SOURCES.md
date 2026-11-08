```markdown
# DATA_SOURCES

ship2shore_rag ingests only documents the operator may lawfully use. The committed snapshot `snapshots/ship2shore.sqlite3` (generated 2026-08-26; 125 documents, 1,571 chunks, SHA-256 ee33c7e9...bea) is a mixed-licence compilation; each source keeps its own terms. Regenerate with `cli.py export-sqlite`.

## Sources in the snapshot
| source key | Publisher | URL pattern | Licence | Docs / chars | Fields stored | Coverage | Refresh | Caveats | Method |
|---|---|---|---|---|---|---|---|---|---|
| arxiv | arXiv / Cornell | export.arxiv.org API | metadata CC0; papers per-author licence | 97 / 110K (abstracts) | title, url, abstract chunks | seed queries on shipping/logistics/casualty analysis | on demand | ~70/97 off-topic (CERN SHiP, control, LLMs): tighten queries, require maritime terms | `cli.py ingest --source arxiv` |
| wikipedia | Wikimedia | en.wikipedia.org/wiki/<title> | CC BY-SA 4.0 | 14 / 298K | text chunks | curated maritime topics | on demand | share-alike; keep revision IDs | MediaWiki API |
| maib | UK MAIB | gov.uk/maib-reports.atom -> assets.publishing.service.gov.uk PDFs | Open Government Licence v3.0 | 7 / 633K | full report text | 2026-12..2026-18 reports | on demand | embedded third-party images; attribution statement required | Atom feed + pypdf |
| pdf (ntsb) | US NTSB | ntsb.gov/investigations/AccidentReports/Reports/MIR*.pdf | US gov work, public domain | 3 / 707K | full report text | Dali/Key Bridge, Ocean Navigator, Baylor J. Tregre | curated + CAROL discovery | CAROL JSON API undocumented | `ingest --source ntsb|pdf` |
| ntm | UKHO ADMIRALTY | msi.admiralty.co.uk/NoticesToMariners/Weekly (token per load) | UKHO Crown copyright; free to download, redistribution unverified | 1 / 571K | weekly booklet text | week 36/2026 | weekly | REMOVE from public snapshot until terms confirmed | two-step token fetch |
| file | operator | local path | operator's own | 3 / 0.5K | demo fixtures | demo only | - | records local scratch path | `--source file` |

## Optional (config-driven, not in snapshot)
- `taic`: NZ TAIC reports (NZ Crown copyright, acknowledge source).
- IMO convention pages, UNCTAD RMT page via Jina Reader: licence "verify", do not redistribute.
- DNV class rules (RU-SHIP): free download, not crawlable, local use only.

## Never ingest into a public snapshot
ICC Incoterms and UCP600/URDG, BIMCO contract forms, carrier bills of lading/terms, paid IMO publications, SIRE/vetting reports, class-society proprietary rules, PMS manuals.

## Software models
sentence-transformers/all-MiniLM-L6-v2 (embeddings), cross-encoder/ms-marco-MiniLM-L-6-v2 (rerank). Check model-card licences before redistribution.

## Attribution text
"Contains public sector information licensed under the Open Government Licence v3.0 (MAIB). Wikipedia text under CC BY-SA 4.0, authors via page history. NTSB reports are US government works."
```
