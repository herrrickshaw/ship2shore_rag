# Gates: automated NTSB crawler (investigate first, implement only if real)

Scope: determine — via a REAL investigation, not an assumption carried over
from the README's existing claim that "CAROL's API isn't public/documented"
— whether data.ntsb.gov's CAROL marine-accident search has any stable,
usable endpoint. If yes, ship a working `fetch_ntsb()` in
ingest/sources.py, additive only. If genuinely no, ABANDON with real
evidence from the attempt (a request URL and what came back, or a
concrete description of what blocked it — auth wall, session token,
obfuscated payload, etc.) — not a restatement of the prior assumption.

- [x] G1: investigated the CAROL search UI (https://data.ntsb.gov/carol-main-public/basic-search, Mode=Marine) via the Browser tool's network-request inspection while performing a real search, and recorded what was actually observed (request URL(s), method, response shape/status) — the deciding evidence line must quote real captured request/response data, not a description of what the page "probably" does
  EVIDENCE: Loaded https://data.ntsb.gov/carol-main-public/basic-search live in the Browser tool, set the "Mode" combo-box to "Marine" via real clicks, clicked Search. read_network_requests captured (tabId tab-2):
    POST https://data.ntsb.gov/carol-main-public/api/Session/CreateSession -> 200
    GET  https://data.ntsb.gov/carol-main-public/api/Query/BasicSearchTemplate -> 200
    POST https://data.ntsb.gov/carol-main-public/api/Lookup/ValueOption/Search/Columns -> 200
    POST https://data.ntsb.gov/carol-main-public/api/Query/Main -> 200
  Fetched the actual response body of that Query/Main POST via read_network_requests(requestId="50043.465", tabId="tab-2") and it returned real, structured JSON case data, e.g. the first record verbatim:
    {"Fields":[{"FieldName":"NtsbNo","Values":["DCA26FM018"]},{"FieldName":"Mkey","Values":["203281"]},{"FieldName":"EventDate","Values":["2026-06-28T10:26:00Z"]},{"FieldName":"City","Values":["Woods Hole"]},{"FieldName":"State","Values":["Massachusetts"]},{"FieldName":"Mode","Values":["Marine"]},{"FieldName":"ReportType","Values":["DirectorBrief"]}, ...],"EntryId":"6a8e8ad95126d4a009a8dd91"}
    The page showed "Search Results: 588" for Mode=Marine. No login, no auth header, no API key visible anywhere in the request — the site does load Cloudflare's cdn-cgi/challenge-platform/h/b/scripts/jsd/... script, so bot-management is present, but it did not block the calls.
  Reverse-engineered the exact request contract by reading the app's own unminified client source (fetched live, not guessed): build/dev/wwwroot/custom-components/pages/basic-search-page.js (query object + _search()), search-results.js (iron-ajax id="search" body="[[listSearchQuery]]"), results-list-view.js (listSearchQuery shape: ResultSetSize/ResultSetOffset/QueryGroups/AndOr/SortColumn/SortDescending/TargetCollection/SessionId), and confirmed api/Session/CreateSession (returns a bare integer, e.g. 1019888) is what supplies SessionId — omitting it makes api/Query/Main 500 with body "An unknown exception occured.", proving it's required, not decorative.
  Then replicated the WHOLE flow from a bare Python `requests.Session()` (no browser, no JS execution, no cookies pre-seeded) run via Bash:
    CreateSession: 200 1019889
    BasicSearchTemplate: 200 {"QueryGroups":[...]}
    POST api/Query/Main -> status 200, 5/5 real results incl. ['DCA26FM018'] ['203281'] ['2026-06-28T10:26:00Z'] ['Marine']
  This is the deciding evidence: the plain, unauthenticated `requests` call from outside the browser got the same real data the browser got, with zero Cloudflare challenge triggered — CAROL's search grid sits on a genuinely public, stable (if undocumented) JSON API. The README's "private JS API, not usable" claim was WRONG for the current site (verified live 2026-08-26); it may have been true at an earlier point or under different bot-management config, but is not true now.

- [x] G2: IF a usable endpoint was found — fetch_ntsb() added to ingest/sources.py (additive: does not modify fetch_arxiv/fetch_maib/fetch_pdf/fetch_wikipedia), returns real report dicts shaped like every other fetcher: {"source","url","title","text","license","published_at"}
  CHECK: cd /Users/umashankar/repos/ship2shore_rag && .venv/bin/python3 -c "from ingest.sources import fetch_ntsb; docs = fetch_ntsb(max_results=3); print(len(docs), docs[0].keys() if docs else None)"
  EXPECT: applies — endpoint found in G1. Command should print `3 dict_keys(['source', 'url', 'title', 'text', 'license', 'published_at'])`.
  EVIDENCE: Ran the exact CHECK command. Output: `3 dict_keys(['source', 'url', 'title', 'text', 'license', 'published_at'])`. Inspected full doc content (not just keys) for all 3: real ntsb.gov PDF URLs (MIR2625.pdf, MIR2622.pdf, MIR2609.pdf), non-empty titles built from report number + city/state ("NTSB Marine Accident Report MIR2625 — Maine"), license "U.S. government work — public domain (17 U.S.C. Sec 105)", real ISO published_at dates pulled from the API's ReportDate field, and extracted PDF text of 21565/30475/23268 characters each starting with genuine report prose, e.g. MIR2625: "Fire aboard Fishing Vessel GITN'R DUN   On July 24, 2025, about 0900 local time, a fire broke out in the engine compartment aboard the fishing vessel GITN'R DUN...". Confirmed via `git diff --stat ingest/sources.py` that the only change is the new fetch_ntsb() function plus 3 new module-level constants (NTSB_CAROL_BASE, NTSB_REPORT_BASE, NTSB_REPORT_NUMBER_RE) — fetch_arxiv/fetch_maib/fetch_pdf/fetch_wikipedia/fetch_ntm/fetch_pdf_sources are all byte-for-byte untouched (diff shows only additions, no deletions/modifications to existing lines).

- [x] G3: IF found — live-tested: fetch_ntsb() returns genuinely different reports than the 3 already hand-curated in ingest/sources.yaml (MIR2540/MIR2513/MIR2521), proving it discovers reports rather than just replaying the same 3 URLs
  EVIDENCE: Ran `fetch_ntsb(max_results=15)` live and diffed the returned report numbers against the hand-curated set {"MIR2540","MIR2513","MIR2521"} from ingest/sources.yaml. Result:
    fetched report numbers: ['MIR2625', 'MIR2622', 'MIR2609', 'MIR2620', 'MIR2617', 'MIR2621', 'MIR2607', 'MIR2611', 'MIR2603', 'MIR2604', 'MIR2601', 'MIR2532', 'MIR2606', 'MIR2608', 'MIR2602']
    overlap with hand-curated 3: set()  (empty)
    new/different reports discovered: 15 of 15
  Separately measured the full discoverable pool: querying Mode=Marine with ResultSetSize=1000 returns all 588 marine cases currently in CAROL; of those, 457 carry a ReportNumber matching a real report pattern (not "Closeout"/"Memo"/"NA" placeholders), broken down by prefix as MAB=264, MIR=167, MAR=22, SA=3, MA=1 (SA/MA don't resolve to real PDFs at the ntsb.gov URL pattern and are filtered out by fetch_ntsb()'s Content-Type HEAD check; MIR/MAB/MAR do — spot-checked one of each: MAB2126.pdf and MAR2105.pdf both returned Content-Type application/pdf, status 200). So fetch_ntsb() discovers roughly two orders of magnitude more real marine reports than the 3 that were hand-curated, not a replay of the same 3 URLs.

ABANDON: G4 not applicable — a usable, unauthenticated JSON endpoint was found and confirmed live (G1), so the "IF NOT found" branch this gate covers does not apply. No abandonment occurred; see G1-G3 for the positive finding.

- [x] G5: whichever outcome, README's Sources section is left internally consistent — draft the exact wording change (driver will apply it at integration; this leaf does not edit README.md directly per the file-ownership contract) and hand it to the driver as part of your final report
  EVIDENCE: Current README/sources.yaml wording (comment block at top of ingest/sources.yaml, mirrored in spirit by README's Sources section) reads:
    "NTSB marine accident reports are U.S. government works (17 U.S.C. §105 —
    public domain) but NTSB has no stable public feed like MAIB's Atom feed:
    its search UI (CAROL, data.ntsb.gov) is a private JS API, not a documented
    one."
  This is now factually superseded. Drafted replacement (handed to driver in final report, not applied here per file-ownership contract — README.md and sources.yaml's header comment are both out of scope for this leaf):
    "NTSB marine accident reports are U.S. government works (17 U.S.C. §105 —
    public domain). NTSB has no *documented* public API, but CAROL's search UI
    (data.ntsb.gov/carol-main-public) is backed by a plain, unauthenticated JSON
    endpoint (api/Query/Main, after a throwaway api/Session/CreateSession call)
    that ingest/sources.py's fetch_ntsb() queries directly (Mode=Marine),
    discovering and downloading report PDFs (MIR/MAB/MAR-prefixed) beyond the
    hand-picked ones below. Verified live 2026-08-26; if NTSB changes CAROL's
    internals this may need re-verifying."

<!--
Leaf brief context: this is a genuine investigation, not a rubber-stamp.
Use the Browser tool (preview_start with url, read_network_requests,
read_page/get_page_text) to actually load
https://data.ntsb.gov/carol-main-public/basic-search, set Mode=Marine (or
navigate directly to whatever URL performs that search), and watch the
network panel for the XHR/fetch calls the page itself makes to populate
results. Many "private" search UIs still hit a plain JSON endpoint
underneath even without documented API docs — that is worth checking for
real before concluding otherwise. If a session cookie or CSRF token is
required, note whether it's obtainable from an unauthenticated page load
(usable) or requires a login (not usable, genuine ABANDON reason). Report
back to the driver with the raw evidence either way — this is the leaf
whose "done" most depends on honesty about what was actually found rather
than what was expected.
-->
