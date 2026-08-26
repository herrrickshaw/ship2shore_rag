"""Fetchers for free, legally accessible maritime/shipping literature.

Each fetcher returns a list of dicts: {"source", "url", "title", "text", "license"}.
No paywalled or ToS-restricted sites are scraped here — add those yourself in
sources.yaml only if you have the right to ingest them.
"""

import io
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
import yaml
from pypdf import PdfReader

USER_AGENT = "ship2shore_rag/0.1 (research tool; contact via GitHub issue)"
HEADERS = {"User-Agent": USER_AGENT}

ARXIV_API = "http://export.arxiv.org/api/query"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
MAIB_FEED = "https://www.gov.uk/maib-reports.atom"
UKHO_NTM_WEEKLY = "https://msi.admiralty.co.uk/NoticesToMariners/Weekly"
UKHO_NTM_DOWNLOAD = "https://msi.admiralty.co.uk/NoticesToMariners/DownloadFile"
NTSB_CAROL_BASE = "https://data.ntsb.gov/carol-main-public"
NTSB_REPORT_BASE = "https://www.ntsb.gov/investigations/AccidentReports/Reports"
NTSB_REPORT_NUMBER_RE = re.compile(r"^[A-Z]{2,5}\d{2,6}$")
JINA_READER_BASE = "https://r.jina.ai/"
READER_PUBLISHED_RE = re.compile(r"^Published Time:\s*(.+)$", re.MULTILINE)
# e.g. DownloadFile?fileName=36wknm26.pdf&amp;batchId=<uuid>&amp;mimeType=... — matches
# only the main weekly booklet ("wknm"), not the per-chart correction PDFs also
# listed on the same page.
NTM_LINK_PATTERN = r"DownloadFile\?fileName=(\d+wknm\d+\.pdf)&amp;batchId=([\w-]+)"

DEFAULT_ARXIV_QUERIES = [
    "container shipping logistics",
    "maritime accident root cause analysis",
    "maritime casualty investigation retrieval augmented generation",
    "ship collision risk prediction",
    "port state control detention prediction",
    "vessel traffic service large language model",
    "maritime autonomous surface ship safety",
    "maritime domain large language model",
    "ship accident human factors analysis",
]

DEFAULT_WIKIPEDIA_TITLES = [
    "Containerization",
    "Bill of lading",
    "Charterparty",
    "Freight rate",
    "Baltic Dry Index",
    "International Maritime Organization",
    "SOLAS Convention",
    "MARPOL",
    "Flag of convenience",
    "Port state control",
    "Demurrage",
    "General average",
    "Ship agent",
    "Bulk carrier",
    "Container ship",
    "Panamax",
]


def fetch_arxiv(query: str, max_results: int = 20) -> list[dict]:
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
    }
    resp = None
    for attempt, backoff in enumerate((0, 10, 30)):
        if backoff:
            time.sleep(backoff)
        resp = requests.get(ARXIV_API, params=params, headers=HEADERS, timeout=30)
        if resp.status_code != 429:
            break
    resp.raise_for_status()
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(resp.text)
    out = []
    for entry in root.findall("atom:entry", ns):
        title = entry.findtext("atom:title", default="", namespaces=ns).strip()
        summary = entry.findtext("atom:summary", default="", namespaces=ns).strip()
        url = entry.findtext("atom:id", default="", namespaces=ns).strip()
        published = entry.findtext("atom:published", default=None, namespaces=ns)
        if not url or not summary:
            continue
        out.append(
            {
                "source": "arxiv",
                "url": url,
                "title": title,
                "text": summary,
                "license": "arXiv non-exclusive license",
                "published_at": published,
            }
        )
    return out


def fetch_arxiv_seed(
    queries: list[str] | None = None, max_results_per_query: int = 15
) -> list[dict]:
    """Runs the built-in seed queries — general maritime/shipping literature plus
    casualty/accident-analysis literature (the most active academic RAG sub-area
    per the market survey) — and dedupes across queries by URL."""
    queries = queries or DEFAULT_ARXIV_QUERIES
    seen: set[str] = set()
    out = []
    for query in queries:
        try:
            results = fetch_arxiv(query, max_results_per_query)
        except Exception as e:
            print(f"  skipping query {query!r}: {type(e).__name__}: {e}")
            continue
        for doc in results:
            if doc["url"] in seen:
                continue
            seen.add(doc["url"])
            out.append(doc)
        time.sleep(3)  # arXiv's API usage policy asks for >=3s between requests
    return out


def fetch_wikipedia(titles: list[str] | None = None) -> list[dict]:
    titles = titles or DEFAULT_WIKIPEDIA_TITLES
    out = []
    for title in titles:
        params = {
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "titles": title,
            "format": "json",
        }
        resp = None
        for attempt, backoff in enumerate((0, 5, 20)):
            if backoff:
                time.sleep(backoff)
            resp = requests.get(WIKIPEDIA_API, params=params, headers=HEADERS, timeout=30)
            if resp.status_code != 429:
                break
        if resp.status_code == 429:
            print(f"  skipping {title!r}: still rate-limited after retries")
            continue
        resp.raise_for_status()
        time.sleep(0.5)  # be polite to the shared Wikipedia API
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            extract = page.get("extract", "")
            if not extract:
                continue
            page_title = page.get("title", title)
            url = f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}"
            out.append(
                {
                    "source": "wikipedia",
                    "url": url,
                    "title": page_title,
                    "text": extract,
                    "license": "CC BY-SA 4.0",
                }
            )
    return out


def fetch_maib(max_results: int = 30) -> list[dict]:
    """UK Marine Accident Investigation Branch reports — public sector info,
    Open Government Licence. Discovered via gov.uk's Atom feed (stable, no
    scraping of paginated search HTML), then each report's PDF is resolved
    from its detail page."""
    resp = requests.get(MAIB_FEED, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(resp.text)

    out = []
    for entry in root.findall("atom:entry", ns)[:max_results]:
        title = entry.findtext("atom:title", default="", namespaces=ns).strip()
        updated = entry.findtext("atom:updated", default=None, namespaces=ns)
        link_el = entry.find("atom:link[@rel='alternate']", ns)
        detail_url = link_el.get("href") if link_el is not None else None
        if not detail_url:
            continue

        detail_resp = requests.get(detail_url, headers=HEADERS, timeout=30)
        time.sleep(0.5)  # be polite to gov.uk
        if detail_resp.status_code != 200:
            continue
        match = re.search(r'href="([^"]+\.pdf)"', detail_resp.text)
        if not match:
            continue

        doc = fetch_pdf(match.group(1), title=title, license="Open Government Licence v3.0")
        if doc:
            doc["source"] = "maib"
            doc["published_at"] = updated
            out.append(doc)
        time.sleep(0.5)
    return out


def fetch_ntm(max_results: int = 10) -> list[dict]:
    """UKHO ADMIRALTY weekly Notices to Mariners — the current week's main
    bulletin booklet only (not the hundreds of individual per-chart correction
    PDFs also listed on the same page, which are numeric/geometric corrections,
    not text literature). Freely downloadable, no login — UKHO generates a
    fresh batchId token per page load that the download URL must reuse, so
    this is a two-step fetch (index page, then each PDF) rather than a stable
    feed like MAIB's."""
    resp = requests.get(UKHO_NTM_WEEKLY, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    matches = re.findall(NTM_LINK_PATTERN, resp.text)[:max_results]

    out = []
    for filename, batch_id in matches:
        url = (
            f"{UKHO_NTM_DOWNLOAD}?fileName={filename}&batchId={batch_id}"
            "&mimeType=application%2Fpdf&frequency=Weekly"
        )
        doc = fetch_pdf(
            url,
            title=f"ADMIRALTY Notices to Mariners — Weekly Edition ({filename})",
            license="UKHO/ADMIRALTY — freely downloadable for navigational use; verify terms before redistribution",
        )
        if doc:
            doc["source"] = "ntm"
            out.append(doc)
        time.sleep(0.5)
    return out


def fetch_ntsb(max_results: int = 30) -> list[dict]:
    """NTSB marine-accident investigation reports — U.S. government works, public
    domain under 17 U.S.C. Sec 105 (same basis as the hand-curated MIR entries
    already in sources.yaml).

    NTSB's CAROL search UI (data.ntsb.gov/carol-main-public) has no published
    API docs, but it's a Vaadin/Polymer single-page app whose search grid is
    populated by a plain, unauthenticated JSON endpoint underneath
    (api/Query/Main), reached after a throwaway api/Session/CreateSession call
    — confirmed live via the browser's network panel while running a real
    Mode=Marine search, then replicated with a bare requests.Session() with no
    cookies/login/API key and no Cloudflare challenge in the way. We query it
    filtered to Mode=Marine, keep only cases whose ReportNumber looks like a
    real published report (e.g. "MIR2625", "MAB2126", "MAR2105" — CAROL also
    returns non-report placeholders like "Closeout"/"Memo"/"NA" for cases with
    no PDF, which this filters out), and download each report PDF from the
    same predictable ntsb.gov URL pattern already used for the 3 hand-curated
    entries. A HEAD request confirms a real PDF before downloading, since
    ntsb.gov returns HTTP 200 with an HTML "not found" page (not a 404) for a
    guessed report number that doesn't exist."""
    session = requests.Session()
    session.headers.update(HEADERS)

    resp = None
    for attempt, backoff in enumerate((0, 10, 30)):
        if backoff:
            time.sleep(backoff)
        resp = session.post(f"{NTSB_CAROL_BASE}/api/Session/CreateSession", timeout=30)
        if resp.status_code != 429:
            break
    resp.raise_for_status()
    session_id = resp.json()

    template_resp = session.get(f"{NTSB_CAROL_BASE}/api/Query/BasicSearchTemplate", timeout=30)
    template_resp.raise_for_status()
    query = template_resp.json()
    mode_rule = next(r for r in query["QueryGroups"][0]["QueryRules"] if r["FieldName"] == "Mode")
    mode_rule["Values"] = ["Marine"]

    search_body = {
        "ResultSetSize": 1000,  # currently ~590 total marine cases; comfortably above that
        "ResultSetOffset": 0,
        "QueryGroups": query["QueryGroups"],
        "AndOr": "And",
        "SortColumn": None,
        "SortDescending": True,
        "TargetCollection": "cases",
        "SessionId": session_id,
    }
    search_resp = session.post(f"{NTSB_CAROL_BASE}/api/Query/Main", json=search_body, timeout=60)
    search_resp.raise_for_status()
    cases = search_resp.json().get("Results", [])

    out = []
    for case in cases:
        if len(out) >= max_results:
            break
        fields = {f["FieldName"]: f["Values"] for f in case.get("Fields", [])}
        report_numbers = fields.get("ReportNumber") or []
        if not report_numbers or not NTSB_REPORT_NUMBER_RE.match(report_numbers[0]):
            continue
        report_no = report_numbers[0]
        url = f"{NTSB_REPORT_BASE}/{report_no}.pdf"

        try:
            head = session.head(url, timeout=30, allow_redirects=True)
        except requests.exceptions.RequestException as e:
            print(f"  skipping {report_no}: {type(e).__name__}: {e}")
            continue
        if head.status_code != 200 or "pdf" not in head.headers.get("Content-Type", "").lower():
            continue  # soft-404: ntsb.gov serves an HTML page with status 200 for a missing report

        city = (fields.get("City") or [""])[0]
        state = (fields.get("State") or [""])[0]
        location = ", ".join(p for p in (city, state) if p)
        title = f"NTSB Marine Accident Report {report_no}" + (f" — {location}" if location else "")
        published_at = (fields.get("ReportDate") or fields.get("EventDate") or [None])[0]

        try:
            doc = fetch_pdf(
                url, title=title, license="U.S. government work — public domain (17 U.S.C. Sec 105)"
            )
        except Exception as e:
            print(f"  skipping {report_no}: {type(e).__name__}: {e}")
            continue
        if doc:
            doc["source"] = "ntsb"
            doc["published_at"] = published_at
            out.append(doc)
        time.sleep(0.5)  # be polite to ntsb.gov
    return out


def fetch_pdf(url: str, title: str | None = None, license: str | None = None) -> dict | None:
    resp = None
    last_error = None
    for attempt, backoff in enumerate((0, 5, 15)):
        if backoff:
            time.sleep(backoff)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=90)
            resp.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            last_error = e
            resp = None
    if resp is None:
        raise last_error
    reader = PdfReader(io.BytesIO(resp.content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    text = text.replace(
        "\x00", ""
    )  # malformed PDFs can yield NUL bytes; Postgres text columns reject them
    if not text.strip():
        return None
    return {
        "source": "pdf",
        "url": url,
        "title": title or url.rsplit("/", 1)[-1],
        "text": text,
        "license": license or "unspecified — verify before redistribution",
    }


def fetch_url_via_reader(
    url: str, title: str | None = None, license: str | None = None
) -> dict | None:
    """Fetches an arbitrary public HTML page as clean markdown via Jina AI
    Reader (r.jina.ai) instead of raw scraping — future-proofs sources.yaml
    for HTML sources (port authority pages, IMO circulars, industry white
    papers) that fetch_pdf()'s pypdf extraction can't handle, since it isn't
    a PDF. Free tier, no API key. Routes the URL through Jina's servers,
    which is fine for public web pages but NOT appropriate for licensed/
    restricted documents — use `--source file` for those instead, which
    never leaves this machine."""
    resp = None
    last_error = None
    for attempt, backoff in enumerate((0, 5, 20)):
        if backoff:
            time.sleep(backoff)
        try:
            resp = requests.get(f"{JINA_READER_BASE}{url}", headers=HEADERS, timeout=60)
            resp.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            last_error = e
            resp = None
    if resp is None:
        raise last_error
    text = resp.text
    if not text.strip():
        return None
    return {
        "source": "pdf",  # same sources.yaml-curated bucket as fetch_pdf(), just a different underlying fetch mechanism
        "url": url,
        "title": title or url.rsplit("/", 1)[-1],
        "text": text,
        "license": license or "unspecified — verify before redistribution",
        "published_at": _extract_reader_published_at(text),
    }


def _extract_reader_published_at(text: str) -> str | None:
    """Jina Reader's "Published Time:" header line isn't guaranteed to be
    ISO-8601 (it's whatever the source page's own metadata says) — but
    retriever.py's _passage_date() parses published_at with the strict
    datetime.fromisoformat(), same as arxiv/maib's clean ISO strings expect.
    Validate here rather than downstream, so a malformed date from some
    page's metadata can never surface as a crash in `ask --since ...` later
    — worth losing an occasional date to a parse failure, not worth a
    retrieval-time crash for it."""
    match = READER_PUBLISHED_RE.search(text)
    if not match:
        return None
    raw = match.group(1).strip()
    try:
        datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return raw


def fetch_pdf_sources(config_path: str) -> list[dict]:
    with open(config_path) as f:
        cfg = yaml.safe_load(f) or {}
    out = []
    for entry in cfg.get("pdf_sources", []):
        fetcher = fetch_url_via_reader if entry.get("type") == "html" else fetch_pdf
        try:
            doc = fetcher(entry["url"], entry.get("title"), entry.get("license"))
        except Exception as e:
            print(f"  skipping {entry['url']}: {type(e).__name__}: {e}")
            continue
        if doc:
            out.append(doc)
    return out
