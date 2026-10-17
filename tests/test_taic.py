from ingest import registry, sources
from ingest.sources import TAIC_INQUIRY_RE, parse_taic_inquiry

PUBLISHED = """
<title>Fishing vessel, Chokyu Maru No.68 Grounding The Noises, Hauraki Gulf | TAIC</title>
<dl><div class="metadata__item"><dt class="metadata__label">Published date</dt>
<dd class="metadata__value">19 June 2025</dd></div></dl>
<a href="/sites/default/files/reports/2025-09/MO-2024-203%20Final%20Report.pdf">Download</a>
<a href="https://wwwcdn.imo.org/x/A.893(21).pdf">unrelated</a>
"""

IN_PROGRESS = """
<title>F/V Taudre Grounding | TAIC</title>
<dt class="metadata__label">Published date</dt><dd class="metadata__value">Not yet published</dd>
"""


def test_parse_published_inquiry():
    info = parse_taic_inquiry(PUBLISHED)
    assert info["pdf_path"] == "/sites/default/files/reports/2025-09/MO-2024-203%20Final%20Report.pdf"
    assert info["published_at"] == "2025-06-19"
    assert info["title"].startswith("Fishing vessel, Chokyu Maru")


def test_in_progress_inquiry_has_no_report():
    assert parse_taic_inquiry(IN_PROGRESS) is None


def test_unparseable_date_becomes_none_not_crash():
    html = PUBLISHED.replace("19 June 2025", "sometime")
    assert parse_taic_inquiry(html)["published_at"] is None


def test_listing_regex_only_matches_maritime_inquiries():
    html = '<a href="/inquiry/mo-2025-201">m</a><a href="/inquiry/ao-2026-002">a</a><a href="/inquiry/ro-2026-104">r</a>'
    assert TAIC_INQUIRY_RE.findall(html) == ["/inquiry/mo-2025-201"]


class _Resp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        pass


def test_fetch_taic_respects_max_results_and_skips_unpublished(monkeypatch):
    def fake_get(url, params=None, **_):
        if "inquiries-recommendations" in url:
            return _Resp('<a href="/inquiry/mo-2025-206">x</a><a href="/inquiry/mo-2024-203">y</a>')
        return _Resp(IN_PROGRESS if url.endswith("mo-2025-206") else PUBLISHED)

    monkeypatch.setattr(sources.requests, "get", fake_get)
    monkeypatch.setattr(sources.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        sources, "fetch_pdf", lambda url, title=None, license=None: {"source": "pdf", "url": url, "title": title, "text": "t", "license": license}
    )
    docs = sources.fetch_taic(max_results=1)
    assert len(docs) == 1
    d = docs[0]
    assert d["source"] == "taic" and d["published_at"] == "2025-06-19"
    assert d["url"].startswith("https://www.taic.org.nz/sites/default/files/reports/")
    assert "TAIC MO-2024-203" in d["title"]


def test_taic_registered():
    assert "taic" in registry.REGISTRY
