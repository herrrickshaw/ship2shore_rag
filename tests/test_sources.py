from ingest.sources import DEFAULT_WIKIPEDIA_TITLES


def test_default_wikipedia_titles_nonempty():
    assert len(DEFAULT_WIKIPEDIA_TITLES) > 5
    assert all(isinstance(t, str) and t for t in DEFAULT_WIKIPEDIA_TITLES)
