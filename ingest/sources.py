"""Fetchers for free, legally accessible maritime/shipping literature.

Each fetcher returns a list of dicts: {"source", "url", "title", "text", "license"}.
No paywalled or ToS-restricted sites are scraped here — add those yourself in
sources.yaml only if you have the right to ingest them.
"""
import io
import re
import time
import xml.etree.ElementTree as ET

import requests
import yaml
from pypdf import PdfReader

USER_AGENT = "ship2shore_rag/0.1 (research tool; contact via GitHub issue)"
HEADERS = {"User-Agent": USER_AGENT}

ARXIV_API = "http://export.arxiv.org/api/query"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
MAIB_FEED = "https://www.gov.uk/maib-reports.atom"

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
    resp = requests.get(ARXIV_API, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(resp.text)
    out = []
    for entry in root.findall("atom:entry", ns):
        title = entry.findtext("atom:title", default="", namespaces=ns).strip()
        summary = entry.findtext("atom:summary", default="", namespaces=ns).strip()
        url = entry.findtext("atom:id", default="", namespaces=ns).strip()
        if not url or not summary:
            continue
        out.append(
            {
                "source": "arxiv",
                "url": url,
                "title": title,
                "text": summary,
                "license": "arXiv non-exclusive license",
            }
        )
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
            out.append(doc)
        time.sleep(0.5)
    return out


def fetch_pdf(url: str, title: str | None = None, license: str | None = None) -> dict | None:
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    reader = PdfReader(io.BytesIO(resp.content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not text.strip():
        return None
    return {
        "source": "pdf",
        "url": url,
        "title": title or url.rsplit("/", 1)[-1],
        "text": text,
        "license": license or "unspecified — verify before redistribution",
    }


def fetch_pdf_sources(config_path: str) -> list[dict]:
    with open(config_path) as f:
        cfg = yaml.safe_load(f) or {}
    out = []
    for entry in cfg.get("pdf_sources", []):
        try:
            doc = fetch_pdf(entry["url"], entry.get("title"), entry.get("license"))
        except Exception as e:
            print(f"  skipping {entry['url']}: {type(e).__name__}: {e}")
            continue
        if doc:
            out.append(doc)
    return out
