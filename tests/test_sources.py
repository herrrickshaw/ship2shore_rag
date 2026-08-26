import re

from ingest.sources import DEFAULT_ARXIV_QUERIES, DEFAULT_WIKIPEDIA_TITLES, NTM_LINK_PATTERN


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
