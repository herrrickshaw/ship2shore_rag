from retrieval.diversify import select


def _passage(url: str, content: str) -> dict:
    return {"url": url, "content": content, "title": url}


def test_caps_results_per_source():
    contents = [
        "the engine room fire started near the auxiliary generator",
        "customs clearance delays affected the cargo manifest",
        "the crew conducted a lifeboat drill before departure",
        "port authorities inspected the ballast water treatment system",
        "the vessel's radar failed during heavy fog conditions",
    ]
    passages = [_passage("http://a", c) for c in contents]
    result = select(passages, top_k=5, max_per_source=2)
    assert len(result) == 2


def test_skips_near_duplicate_content_across_sources():
    base = "the vessel sustained hull damage after striking a submerged object near the harbor"
    passages = [
        _passage("http://a", base),
        _passage("http://b", base + " "),  # trivial whitespace variant, still near-duplicate
        _passage(
            "http://c", "completely unrelated content about bills of lading and freight rates"
        ),
    ]
    result = select(passages, top_k=5)
    urls = [p["url"] for p in result]
    assert "http://a" in urls
    assert "http://b" not in urls  # near-duplicate of a, correctly skipped
    assert "http://c" in urls


def test_stops_at_top_k_even_with_more_candidates():
    contents = [
        "engine room fire suppression system activated automatically",
        "cargo manifest discrepancy discovered during customs inspection",
        "lifeboat drill conducted before scheduled departure",
        "ballast water treatment system failed compliance inspection",
        "radar malfunction reported during dense fog conditions",
        "bridge officer navigation error near shipping lane",
        "hull corrosion detected during routine drydock survey",
        "fuel contamination traced to bunkering supplier error",
        "crew fatigue cited as contributing factor in grounding",
        "mooring line failure during severe weather docking",
    ]
    passages = [_passage(f"http://{i}", c) for i, c in enumerate(contents)]
    result = select(passages, top_k=3)
    assert len(result) == 3


def test_preserves_input_order_for_non_duplicates():
    passages = [
        _passage("http://a", "first distinct passage about engine maintenance"),
        _passage("http://b", "second distinct passage about port logistics"),
        _passage("http://c", "third distinct passage about crew certification"),
    ]
    result = select(passages, top_k=3)
    assert [p["url"] for p in result] == ["http://a", "http://b", "http://c"]


def test_empty_input_returns_empty():
    assert select([], top_k=5) == []


def test_fewer_candidates_than_top_k_returns_all_survivors():
    passages = [_passage("http://a", "only one distinct passage here")]
    result = select(passages, top_k=5)
    assert len(result) == 1
