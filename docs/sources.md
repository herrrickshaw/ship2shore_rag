## Sources

| `--source` | What | License |
|---|---|---|
| `arxiv` | Seed queries (below) if `--query` is omitted, else your own search | arXiv non-exclusive license |
| `wikipedia` | A curated list of maritime-topic articles | CC BY-SA 4.0 |
| `maib` | UK Marine Accident Investigation Branch reports, discovered via `gov.uk/maib-reports.atom` | Open Government Licence v3.0 |
| `ntm` | UKHO ADMIRALTY weekly Notices to Mariners bulletin (the main booklet, not the per-chart correction PDFs) | UKHO/ADMIRALTY — free to download for navigational use; verify terms before redistribution |
| `ntsb` | US NTSB marine accident reports, discovered via CAROL's search API | U.S. government work — public domain (17 U.S.C. §105) |
| `pdf` | Anything in `ingest/sources.yaml` — seeded with a handful of NTSB reports and arXiv papers found by name rather than through the seed queries | varies; verify per entry |
| `file` | Your own local files — see `--path` above | whatever license the file itself carries — verify before ingesting |

NTSB has no *documented* public API, but CAROL's search UI
(`data.ntsb.gov/carol-main-public`) is backed by a plain, unauthenticated JSON
endpoint (`api/Query/Main`, after a throwaway `api/Session/CreateSession`
call) that `fetch_ntsb()` queries directly (`Mode=Marine`), discovering and
downloading report PDFs (`MIR`/`MAB`/`MAR`-prefixed) rather than relying on
hand-curated URLs. Verified live 2026-08-26 (~450 real marine reports
discoverable this way); if NTSB changes CAROL's internals this may need
re-verifying — the small hand-picked set in `ingest/sources.yaml` is kept as
a fallback either way.

UKHO's weekly Notices to Mariners page (`msi.admiralty.co.uk/NoticesToMariners/Weekly`)
issues a fresh download token per page load, so `fetch_ntm()` is a two-step
fetch (load the index page, then download using that token) rather than a
stable feed — and the download itself has been observed to intermittently
drop mid-transfer from this network, which is why `fetch_pdf()` now retries
with backoff (see `ingest/sources.py`).

**Formats with no public source to crawl.** DNV's class rules (RU-SHIP) are
free and public but distributed only as whole-edition ZIP archives, not
individually crawlable chapter links — download an edition from
[rules.dnv.com](https://rules.dnv.com/servicedocuments/dnvpm/packages?category=rulesship),
extract it, and ingest the PDFs you want with `--source file`. PMS (planned
maintenance system) manuals, SIRE 2.0/CDI vetting reports, and statutory
certificates (SOLAS/MARPOL/ISM/ISPS) are per-vessel/per-company private
documents by nature — there is no public corpus of these to fetch, so
`--source file` is the only ingestion path for them, by design.

`ingest/sources.py:DEFAULT_ARXIV_QUERIES` covers general shipping/logistics
literature *and* casualty/accident-analysis literature specifically (root cause
analysis, collision risk, PSC detention prediction, VTS/autonomous-ship safety,
human-factors analysis) — the market survey found this was the most active
academic RAG sub-area, well ahead of commercial deployment in the same domain.

## Adding more literature

Edit `ingest/sources.yaml` — add any publicly accessible PDF or HTML URL (IMO
circulars that are public, port authority reports, MARAD/UNCTAD publications,
industry white papers you have the right to ingest). Entries are PDFs by
default (`pypdf`, entirely local); add `type: html` for a non-PDF page —
those are fetched as clean markdown via [Jina AI
Reader](https://r.jina.ai/) (free tier, no API key) instead of raw HTML
scraping. Run `python3 cli.py ingest --source pdf --config
ingest/sources.yaml` to pull them in. Respect each source's license/terms —
this project only ingests sources that are freely and legally accessible;
it does not scrape paywalled or ToS-restricted sites. `type: html` routes
the URL through Jina's servers, which is fine for public pages but not
appropriate for anything under restricted redistribution terms — use
`--source file` for those instead (never leaves this machine).
