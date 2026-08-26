import re

from ingest import sources
from ingest.sources import (
    DEFAULT_ARXIV_QUERIES,
    DEFAULT_WIKIPEDIA_TITLES,
    NTM_LINK_PATTERN,
    _extract_reader_published_at,
)


def test_default_wikipedia_titles_nonempty():
    assert len(DEFAULT_WIKIPEDIA_TITLES) > 5
    assert all(isinstance(t, str) and t for t in DEFAULT_WIKIPEDIA_TITLES)


def test_default_arxiv_queries_cover_casualty_analysis():
    assert len(DEFAULT_ARXIV_QUERIES) > 5
    joined = " ".join(DEFAULT_ARXIV_QUERIES).lower()
    assert "accident" in joined or "casualty" in joined


def test_ntm_link_pattern_matches_weekly_booklet_only():
    html = (
        '<a href="/NoticesToMariners/DownloadFile?fileName=36wknm26.pdf&amp;'
        'batchId=2f715d5e-ffa1-44d4-93e4-0f7f322bf08f&amp;mimeType=application%2Fpdf">wk</a>'
        '<a href="/NoticesToMariners/DownloadFile?fileName=Chart1442NM4132.pdf&amp;'
        'batchId=2f715d5e-ffa1-44d4-93e4-0f7f322bf08f&amp;mimeType=application%2Fpdf">chart</a>'
    )
    matches = re.findall(NTM_LINK_PATTERN, html)
    assert matches == [("36wknm26.pdf", "2f715d5e-ffa1-44d4-93e4-0f7f322bf08f")]


def test_extract_reader_published_at_valid_iso():
    text = "Title: X\n\nPublished Time: 2024-03-15T12:00:00Z\n\nMarkdown Content:\n..."
    assert _extract_reader_published_at(text) == "2024-03-15T12:00:00Z"


def test_extract_reader_published_at_malformed_is_dropped_not_crashed():
    # not ISO-8601 -- retriever.py's _passage_date() parses this strictly,
    # so a bad date here must be dropped at fetch time, never stored, rather
    # than surfacing as a crash later in `ask --since ...`.
    text = "Published Time: Sun, 15 Jun 2025 not-a-real-date"
    assert _extract_reader_published_at(text) is None


def test_extract_reader_published_at_missing_header():
    assert _extract_reader_published_at("no date header here at all") is None


def test_fetch_pdf_sources_dispatches_html_type_to_reader(tmp_path, monkeypatch):
    config = tmp_path / "sources.yaml"
    config.write_text("""
pdf_sources:
  - url: "https://example.com/report.pdf"
    title: "A PDF"
    license: "public domain"
  - url: "https://example.com/page"
    title: "An HTML page"
    license: "public domain"
    type: html
""")
    pdf_calls = []
    reader_calls = []
    monkeypatch.setattr(
        sources,
        "fetch_pdf",
        lambda url, title=None, license=None: pdf_calls.append(url)
        or {"source": "pdf", "url": url},
    )
    monkeypatch.setattr(
        sources,
        "fetch_url_via_reader",
        lambda url, title=None, license=None: reader_calls.append(url)
        or {"source": "pdf", "url": url},
    )

    docs = sources.fetch_pdf_sources(str(config))

    assert pdf_calls == ["https://example.com/report.pdf"]
    assert reader_calls == ["https://example.com/page"]
    assert len(docs) == 2
