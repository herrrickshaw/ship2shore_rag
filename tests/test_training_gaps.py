from rag import training_gaps as tg


def _cert(cert_id: int) -> dict:
    return {
        "id": cert_id,
        "name": "Jane Doe",
        "rank": "Chief Officer",
        "vessel_name": "MV Tester",
        "stcw_cert_expiry": "2027-01-01",
    }


def test_training_gaps_returns_empty_when_no_certs_expiring(monkeypatch):
    monkeypatch.setattr(tg, "list_expiring_certs", lambda days_ahead: [])
    retrieve_called = []
    monkeypatch.setattr(tg, "retrieve", lambda *a, **k: retrieve_called.append(1) or [])

    assert tg.training_gaps(days_ahead=30) == []
    assert retrieve_called == []  # no point embedding a query with nothing to annotate


def test_training_gaps_annotates_each_cert_with_shared_citations(monkeypatch):
    certs = [_cert(1), _cert(2)]
    monkeypatch.setattr(tg, "list_expiring_certs", lambda days_ahead: certs)

    stcw_passage = {
        "title": "STCW Convention",
        "url": "https://example.org/stcw",
        "score": 0.8,
        "regulation_refs": [{"instrument": "STCW", "detail": "Regulation I/1", "year": None}],
    }
    other_passage = {
        "title": "Unrelated",
        "url": "https://example.org/other",
        "score": 0.5,
        "regulation_refs": [],
    }
    calls = []
    monkeypatch.setattr(
        tg, "retrieve", lambda query, top_k=2: calls.append(query) or [other_passage, stcw_passage]
    )

    gaps = tg.training_gaps(days_ahead=30)

    assert len(calls) == 1  # one shared retrieval call, not one per crew member
    assert len(gaps) == 2
    for g in gaps:
        assert g["stcw_citations"] == [stcw_passage]  # filtered to the STCW-citing passage only


def test_training_gaps_falls_back_to_all_passages_if_none_cite_stcw(monkeypatch):
    monkeypatch.setattr(tg, "list_expiring_certs", lambda days_ahead: [_cert(1)])
    passages = [{"title": "x", "url": "u", "score": 0.1, "regulation_refs": []}]
    monkeypatch.setattr(tg, "retrieve", lambda query, top_k=2: passages)

    gaps = tg.training_gaps(days_ahead=30)
    assert gaps[0]["stcw_citations"] == passages
