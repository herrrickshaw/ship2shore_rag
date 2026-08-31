from rag import similar_incidents as si


def test_find_similar_incidents_delegates_to_retrieve(monkeypatch):
    captured = {}

    def fake_retrieve(query, top_k=3):
        captured["query"] = query
        captured["top_k"] = top_k
        return [{"title": "Grounding report", "url": "https://example.org/x", "score": 0.9}]

    monkeypatch.setattr(si, "retrieve", fake_retrieve)

    result = si.find_similar_incidents("vessel ran aground approaching berth", top_k=2)

    assert captured["query"] == "vessel ran aground approaching berth"
    assert captured["top_k"] == 2
    assert result[0]["title"] == "Grounding report"


def test_find_similar_incidents_default_top_k(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        si, "retrieve", lambda query, top_k=3: captured.setdefault("top_k", top_k) or []
    )
    si.find_similar_incidents("loose grating tripping hazard")
    assert captured["top_k"] == 3
