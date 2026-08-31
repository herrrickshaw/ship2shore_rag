from rag import hazard_brief as hb


def _passage(title: str, refs: list[dict], score: float = 0.5) -> dict:
    return {
        "title": title,
        "url": f"https://example.org/{title}",
        "content": "x",
        "score": score,
        "regulation_refs": refs,
    }


def test_dedupe_refs_drops_repeats_across_passages():
    passages = [
        _passage("A", [{"instrument": "SOLAS", "detail": "Chapter II-1", "year": None}]),
        _passage("B", [{"instrument": "SOLAS", "detail": "Chapter II-1", "year": None}]),
        _passage("C", [{"instrument": "MARPOL", "detail": None, "year": None}]),
    ]
    refs = hb._dedupe_refs(passages)
    assert len(refs) == 2
    assert {r["instrument"] for r in refs} == {"SOLAS", "MARPOL"}


def test_dedupe_refs_handles_no_refs():
    passages = [_passage("A", [])]
    assert hb._dedupe_refs(passages) == []


def test_hazard_brief_composes_query_and_dedupes(monkeypatch):
    captured = {}

    def fake_retrieve(query, top_k=5, source_filter=None):
        captured["query"] = query
        captured["top_k"] = top_k
        captured["source_filter"] = source_filter
        return [
            _passage(
                "Enclosed space entry", [{"instrument": "SOLAS", "detail": None, "year": None}]
            )
        ]

    monkeypatch.setattr(hb, "retrieve", fake_retrieve)

    brief = hb.hazard_brief("enclosed space entry", top_k=3, source_filter="maib")

    assert "enclosed space entry" in captured["query"]
    assert captured["top_k"] == 3
    assert captured["source_filter"] == "maib"
    assert brief["job_description"] == "enclosed space entry"
    assert len(brief["passages"]) == 1
    assert brief["regulation_refs"] == [{"instrument": "SOLAS", "detail": None, "year": None}]
