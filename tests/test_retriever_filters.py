from datetime import date, datetime

from retrieval.retriever import _apply_filters, _passage_date


def _passage(source: str, published_at) -> dict:
    return {"source": source, "published_at": published_at, "content": "x", "url": "http://x"}


def test_passage_date_none():
    assert _passage_date(None) is None


def test_passage_date_from_datetime():
    assert _passage_date(datetime(2024, 3, 15, 12, 0, 0)) == date(2024, 3, 15)


def test_passage_date_from_date():
    assert _passage_date(date(2024, 3, 15)) == date(2024, 3, 15)


def test_passage_date_from_iso_string():
    assert _passage_date("2024-03-15T12:00:00Z") == date(2024, 3, 15)


def test_passage_date_from_iso_string_no_timezone():
    assert _passage_date("2024-03-15T12:00:00") == date(2024, 3, 15)


def test_apply_filters_no_filters_returns_all():
    passages = [_passage("arxiv", "2024-01-01T00:00:00Z"), _passage("wikipedia", None)]
    assert _apply_filters(passages, since=None, source_filter=None) == passages


def test_apply_filters_source_filter():
    passages = [_passage("arxiv", None), _passage("wikipedia", None)]
    result = _apply_filters(passages, since=None, source_filter="arxiv")
    assert len(result) == 1
    assert result[0]["source"] == "arxiv"


def test_apply_filters_since_excludes_older():
    passages = [
        _passage("arxiv", "2020-01-01T00:00:00Z"),
        _passage("arxiv", "2026-01-01T00:00:00Z"),
    ]
    result = _apply_filters(passages, since=date(2025, 1, 1), source_filter=None)
    assert len(result) == 1
    assert result[0]["published_at"] == "2026-01-01T00:00:00Z"


def test_apply_filters_since_excludes_undated_passages():
    # a passage with no known publish date can't be confirmed to satisfy
    # "since X" -- it must be excluded, not silently included.
    passages = [_passage("wikipedia", None)]
    result = _apply_filters(passages, since=date(2020, 1, 1), source_filter=None)
    assert result == []


def test_apply_filters_since_and_source_combined():
    passages = [
        _passage("arxiv", "2026-01-01T00:00:00Z"),
        _passage("wikipedia", "2026-01-01T00:00:00Z"),
        _passage("arxiv", "2020-01-01T00:00:00Z"),
    ]
    result = _apply_filters(passages, since=date(2025, 1, 1), source_filter="arxiv")
    assert len(result) == 1
    assert result[0]["source"] == "arxiv"
    assert result[0]["published_at"] == "2026-01-01T00:00:00Z"
