from datetime import date

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import webui.server as server  # noqa: E402


@pytest.fixture
def client():
    return TestClient(server.app)


FAKE_PASSAGES = [
    {
        "content": "Bulk carriers are cargo ships designed to transport unpackaged bulk cargo.",
        "title": "Bulk carrier",
        "url": "https://en.wikipedia.org/wiki/Bulk_carrier",
        "source": "wikipedia",
        "published_at": date(2024, 1, 1),
        "score": 0.9123,
    },
    {
        "content": "Hull failure investigations often cite corrosion and fatigue cracking.",
        "title": "MAIB report on hull failure",
        "url": None,
        "source": "maib",
        "published_at": None,
        "score": 0.4567,
    },
]


def test_index_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "<script>" in resp.text
    assert "ask-form" in resp.text


def test_ask_returns_passages_from_pipeline(client, monkeypatch):
    captured = {}

    def fake_ask(question, top_k=5, generate=True, rerank=True, since=None, source_filter=None):
        captured["args"] = (question, top_k, generate, rerank, since, source_filter)
        return {"answer": "Bulk carriers are large cargo vessels. [1]", "passages": FAKE_PASSAGES}

    monkeypatch.setattr(server, "ask", fake_ask)

    resp = client.post("/ask", json={"question": "What is a bulk carrier?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Bulk carriers are large cargo vessels. [1]"
    assert len(body["passages"]) == 2
    assert body["passages"][0]["title"] == "Bulk carrier"
    assert body["passages"][0]["score"] == pytest.approx(0.9123)
    assert body["passages"][1]["url"] is None

    question, top_k, generate, rerank, since, source_filter = captured["args"]
    assert question == "What is a bulk carrier?"
    assert top_k == 5
    assert generate is True
    assert rerank is True
    assert since is None
    assert source_filter is None


def test_ask_passes_through_optional_filters(client, monkeypatch):
    captured = {}

    def fake_ask(question, top_k=5, generate=True, rerank=True, since=None, source_filter=None):
        captured["args"] = (question, top_k, generate, rerank, since, source_filter)
        return {"answer": None, "passages": []}

    monkeypatch.setattr(server, "ask", fake_ask)

    resp = client.post(
        "/ask",
        json={
            "question": "engine room fires",
            "top_k": 3,
            "generate": False,
            "rerank": False,
            "since": "2020-01-01",
            "source_filter": "maib",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"answer": None, "passages": []}

    question, top_k, generate, rerank, since, source_filter = captured["args"]
    assert question == "engine room fires"
    assert top_k == 3
    assert generate is False
    assert rerank is False
    assert since == date(2020, 1, 1)
    assert source_filter == "maib"


def test_ask_with_no_passages_returns_empty_list(client, monkeypatch):
    monkeypatch.setattr(
        server, "ask", lambda *a, **k: {"answer": "No documents ingested yet.", "passages": []}
    )
    resp = client.post("/ask", json={"question": "anything"})
    assert resp.status_code == 200
    assert resp.json()["passages"] == []
