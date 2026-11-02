"""retrieve()/ask()/ingest_documents() run end to end on fakes: no DB server, model or API key."""

import hashlib
import json
from pathlib import Path

import pytest

import rag.pipeline as pipeline
import retrieval.retriever as retriever
from ingest import ingest as ingest_mod
from retrieval import sqlite_store

GOLDEN = json.loads((Path(__file__).parent / "golden_sqlite_pipeline.json").read_text())


def fake_embed(texts):
    """Deterministic 384-d unit vectors derived from a hash of each text."""
    out = []
    for t in texts:
        h = hashlib.sha256(t.encode()).digest()
        v = [(h[i % 32] / 255.0) - 0.5 for i in range(384)]
        n = sum(x * x for x in v) ** 0.5
        out.append([x / n for x in v])
    return out


DOCS = [
    {
        "source": "arxiv", "url": "http://a/1", "title": "Hull fatigue", "license": "cc",
        "published_at": "2024-01-02T00:00:00Z",
        "text": "Hull fatigue cracking occurs in welded joints. SOLAS Chapter II-1 requires structural integrity. " * 20,
    },
    {
        "source": "maib", "url": "http://m/1", "title": "Engine room fire", "license": None,
        "published_at": "2023-05-05T00:00:00Z",
        "text": "A fire broke out in the engine room due to fuel leak. MARPOL Annex VI applies to emissions. " * 20,
    },
    {
        "source": "wikipedia", "url": "http://w/1", "title": "Strait of Hormuz", "license": "cc",
        "published_at": None,
        "text": "The Strait of Hormuz is a chokepoint with piracy and navigational hazards. " * 20,
    },
]  # fmt: skip


@pytest.fixture()
def sqlite_corpus(tmp_path, monkeypatch):
    path = str(tmp_path / "corpus.sqlite3")
    monkeypatch.setattr(ingest_mod, "STORAGE_BACKEND", "sqlite")
    monkeypatch.setattr(retriever, "STORAGE_BACKEND", "sqlite")
    first = ingest_mod.ingest_documents(DOCS, sqlite_path=path, embed=fake_embed)
    second = ingest_mod.ingest_documents(DOCS, sqlite_path=path, embed=fake_embed)
    real = sqlite_store.retrieve
    monkeypatch.setattr(
        sqlite_store, "retrieve", lambda q, e, k, f, r: real(q, e, k, f, r, path=path)
    )
    return first, second


def _embed_query(text):
    return fake_embed([text])[0]


def test_ingest_matches_original_counts(sqlite_corpus):
    assert sqlite_corpus == (GOLDEN["ingested"], GOLDEN["reingested"])


@pytest.mark.parametrize("query", sorted(GOLDEN["queries"]))
def test_retrieve_reproduces_original_ranking(sqlite_corpus, query):
    got = retriever.retrieve(query, top_k=3, rerank=False, embed=_embed_query)
    slim = [
        {k: p[k] for k in ("title", "url", "source", "published_at")} | {"score": round(p["score"], 9)}
        for p in got
    ]  # fmt: skip
    assert slim == GOLDEN["queries"][query]


def test_retrieve_source_filter_reproduces_original(sqlite_corpus):
    got = retriever.retrieve(
        "fire", top_k=3, rerank=False, source_filter="maib", embed=_embed_query
    )
    assert [p["url"] for p in got] == GOLDEN["filtered"]


def test_ask_extractive_reproduces_original(sqlite_corpus, monkeypatch):
    monkeypatch.setattr(pipeline, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(pipeline, "log_query", lambda *a, **k: None)
    monkeypatch.setattr(
        pipeline,
        "retrieve",
        lambda q, **kw: retriever.retrieve(q, embed=_embed_query, **kw),
    )
    result = pipeline.ask("hull fatigue welded", rerank=False)
    assert result["answer"] is None
    assert [p["url"] for p in result["passages"]] == GOLDEN["ask_extractive"]["urls"]


def test_build_context_budget_reproduces_original(capsys):
    passages = [{"title": "T", "url": "U", "content": "C" * 50}] * 3
    assert pipeline._build_context(passages, max_chars=120) == GOLDEN["context"]
    assert "dropped 2 of 3 passages" in capsys.readouterr().out


def test_retrieve_uses_injected_backend_and_reranker():
    pool = [
        {"content": "a", "source": "s1", "published_at": None, "url": "u1"},
        {"content": "b", "source": "s2", "published_at": None, "url": "u2"},
    ]
    seen = {}

    def backend(query, top_k, fetch_k, rrf_k):
        seen["args"] = (query, top_k, fetch_k, rrf_k)
        return [dict(p) for p in pool]

    def reranker(query, passages):
        return list(reversed(passages))

    got = retriever.retrieve("q", top_k=2, backend=backend, reranker=reranker)
    assert seen["args"] == ("q", 20, 30, 60)
    assert [p["url"] for p in got] == ["u2", "u1"]


class _FakeCursor:
    def __init__(self, results):
        self.results, self.executed = list(results), []

    def execute(self, sql, params=None):
        self.executed.append(sql)

    def fetchall(self):
        return self.results.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, cursor):
        self.cursor_obj = cursor

    def cursor(self):
        return self.cursor_obj

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_postgres_path_with_fake_connection(monkeypatch):
    monkeypatch.setattr(retriever, "register_vector", lambda conn: None)
    row = lambda i: (i, f"c{i}", f"t{i}", f"u{i}", "arxiv", None, [])  # noqa: E731
    cur = _FakeCursor([[(2,), (1,)], [(1,)], [row(1), row(2)]])
    out = retriever._retrieve_postgres(
        "q", 2, 10, 60, embed=lambda t: [0.0, 1.0], connect=lambda url: _FakeConn(cur)
    )
    assert [p["url"] for p in out] == ["u1", "u2"]  # id 1 is in both lists, so it wins
    assert out[0]["score"] == pytest.approx(1 / 61 + 1 / 60)
    assert "ivfflat.probes" in cur.executed[0]


def test_postgres_path_empty_returns_no_passages(monkeypatch):
    monkeypatch.setattr(retriever, "register_vector", lambda conn: None)
    cur = _FakeCursor([[], []])
    assert (
        retriever._retrieve_postgres(
            "q", 2, 10, 60, embed=lambda t: [0.0], connect=lambda url: _FakeConn(cur)
        )
        == []
    )


PASSAGES = [{"title": "T", "url": "http://x", "content": "body", "score": 1.0}]


def test_ask_uses_injected_generator_without_api_key(monkeypatch):
    monkeypatch.setattr(pipeline, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(pipeline, "log_query", lambda *a, **k: None)
    calls = []

    def generator(system, user):
        calls.append((system, user))
        return "answer [1]"

    result = pipeline.ask(
        "why?", checklist=True, generator=generator, retriever=lambda q, **k: PASSAGES
    )
    assert result == {"answer": "answer [1]", "passages": PASSAGES}
    assert calls[0][0] == pipeline.CHECKLIST_SYSTEM_PROMPT
    assert calls[0][1] == "Sources:\n[1] T (http://x)\nbody\n\nQuestion: why?"


def test_ask_generate_false_skips_injected_generator(monkeypatch):
    monkeypatch.setattr(pipeline, "log_query", lambda *a, **k: None)

    def boom(system, user):
        raise AssertionError("must not be called")

    result = pipeline.ask("why?", generate=False, generator=boom, retriever=lambda q, **k: PASSAGES)
    assert result == {"answer": None, "passages": PASSAGES}


def test_ask_without_key_or_generator_is_extractive(monkeypatch):
    monkeypatch.setattr(pipeline, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(pipeline, "log_query", lambda *a, **k: None)
    result = pipeline.ask("why?", retriever=lambda q, **k: PASSAGES)
    assert result["answer"] is None


def test_prepare_chunks_skips_embedder_for_empty_text():
    def boom(texts):
        raise AssertionError("embedder must not be called")

    assert ingest_mod._prepare_chunks("", boom) == ([], [], [])
