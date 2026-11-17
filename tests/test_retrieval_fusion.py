"""RRF fusion, sparse (FTS5 BM25) behaviour, and retrieve()/rerank/eval orchestration.

All fixtures are tiny in-memory/temp SQLite snapshots with hand-made 8-d embeddings;
no Postgres, no model downloads (the embedder and cross-encoder are faked), no LLM.
"""

import math
import os
import tempfile

import pytest

sqlite_vec = pytest.importorskip("sqlite_vec")
from retrieval import rerank as rerank_mod  # noqa: E402
from retrieval import retriever, sqlite_store  # noqa: E402

DIM = 8


def unit(i: int) -> list[float]:
    v = [0.0] * DIM
    v[i] = 1.0
    return v


def mix(weights: dict[int, float]) -> list[float]:
    v = [0.0] * DIM
    for i, w in weights.items():
        v[i] = w
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


@pytest.fixture
def snapshot(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    os.remove(path)
    monkeypatch.setattr(sqlite_store, "SCHEMA", sqlite_store.SCHEMA.replace("float[384]", f"float[{DIM}]"))

    def build(docs):
        """docs: list of (url, source, published_at, content, embedding)."""
        conn = sqlite_store.connect(path)
        sqlite_store.create_schema(conn)
        for url, source, published, content, emb in docs:
            doc_id = sqlite_store.insert_document(conn, source, url, url.upper(), None, published)
            sqlite_store.insert_chunks(conn, doc_id, [content], [emb])
        conn.commit()
        conn.close()
        return path

    yield build
    if os.path.exists(path):
        os.remove(path)


# ---- RRF arithmetic -----------------------------------------------------------------

def test_rrf_scores_are_sum_of_reciprocal_ranks(snapshot):
    # Dense order for query unit(0): A (identical), B (close), C (far).
    # Sparse: only B and C contain "ballast"; C mentions it twice in a shorter text,
    # so BM25 ranks C above B.
    path = snapshot([
        ("a", "s1", None, "engine room fire drill procedures", unit(0)),
        ("b", "s2", None, "ballast water exchange in the engine room log", mix({0: 0.9, 1: 0.1})),
        ("c", "s3", None, "ballast ballast tanks", unit(1)),
    ])
    k = 60
    res = sqlite_store.retrieve("ballast", unit(0), top_k=3, fetch_k=10, rrf_k=k, path=path)
    scores = {r["url"]: r["score"] for r in res}
    assert scores["a"] == pytest.approx(1 / (k + 0))                 # dense rank 0 only
    assert scores["b"] == pytest.approx(1 / (k + 1) + 1 / (k + 1))   # dense 1, sparse 1
    assert scores["c"] == pytest.approx(1 / (k + 2) + 1 / (k + 0))   # dense 2, sparse 0
    assert [r["url"] for r in res] == ["c", "b", "a"]                # agreement beats one strong side


def test_top_k_truncates_fused_list(snapshot):
    path = snapshot([(f"u{i}", "s", None, f"text {i}", mix({0: 1.0, 1: i * 0.1})) for i in range(5)])
    res = sqlite_store.retrieve("nothingmatches", unit(0), top_k=2, fetch_k=10, path=path)
    assert [r["url"] for r in res] == ["u0", "u1"]                   # dense-only order kept


def test_empty_snapshot_returns_empty(snapshot):
    path = snapshot([])
    assert sqlite_store.retrieve("anything", unit(0), path=path) == []


# ---- sparse side on natural-language questions -------------------------------------------

def test_sparse_side_contributes_for_a_natural_question(snapshot):
    """FTS5 has no stopwords and no stemming, and the query was AND-ed over every
    token, so 'What caused the grounding?' required the literal word 'what' to
    appear in the chunk. The keyword-relevant chunk then got no sparse score at all
    and hybrid retrieval silently degraded to dense-only. With a BM25 fallback the
    chunk that shares the content words is lifted to the top."""
    path = snapshot([
        ("near", "s1", None, "routine port state control inspection checklist", unit(0)),
        ("mid", "s2", None, "weather routing for container ships", mix({0: 0.9, 1: 0.44})),
        ("hit", "s3", None, "the grounding was caused by crew fatigue on the bridge", unit(2)),
    ])
    res = sqlite_store.retrieve("What caused the grounding?", unit(0), top_k=1, fetch_k=10, path=path)
    assert res[0]["url"] == "hit"


def test_all_terms_match_still_preferred(snapshot):
    path = snapshot([
        ("both", "s1", None, "grounding caused by fatigue", unit(3)),
        ("one", "s2", None, "grounding of a tanker", unit(4)),
    ])
    res = sqlite_store.retrieve("grounding fatigue", unit(0), top_k=2, fetch_k=10, path=path)
    assert res[0]["url"] == "both"


# ---- retriever.retrieve orchestration (sqlite backend, fakes for models) ------------------------

@pytest.fixture
def sqlite_backend(monkeypatch, snapshot):
    monkeypatch.setattr(retriever, "STORAGE_BACKEND", "sqlite")
    monkeypatch.setattr(retriever, "embed_query", lambda q: unit(0))
    return snapshot


def test_retrieve_pipeline_filters_then_diversifies(sqlite_backend, monkeypatch):
    path = sqlite_backend([
        ("r1", "maib", "2024-05-01", "fire in the engine room one", unit(0)),
        ("r2", "ntsb", "2019-01-01", "old ntsb fire report", mix({0: 0.95, 1: 0.3})),
        ("r3", "maib", "2023-02-01", "galley fire on a ferry", mix({0: 0.9, 1: 0.43})),
    ])
    calls = {}
    real_retrieve = sqlite_store.retrieve

    def spy(query, emb, top_k, fetch_k, rrf_k):
        calls["pool_k"] = top_k
        return real_retrieve(query, emb, top_k, fetch_k, rrf_k, path=path)

    monkeypatch.setattr(sqlite_store, "retrieve", spy)
    monkeypatch.setattr(retriever, "_cross_encoder_rerank",
                        lambda q, ps: pytest.fail("rerank should be off"))
    from datetime import date
    out = retriever.retrieve("fire", top_k=1, candidate_k=7, rerank=False,
                             since=date(2023, 1, 1), source_filter="maib")
    assert calls["pool_k"] == 7
    assert [p["url"] for p in out] == ["r1"]


def test_retrieve_uses_reranker_order(sqlite_backend, monkeypatch):
    path = sqlite_backend([
        ("x", "s", None, "first by fusion", unit(0)),
        ("y", "s2", None, "second by fusion", mix({0: 0.9, 1: 0.44})),
    ])
    real = sqlite_store.retrieve
    monkeypatch.setattr(sqlite_store, "retrieve", lambda q, e, t, f, k: real(q, e, t, f, k, path=path))

    class FakeCE:
        def predict(self, pairs):
            return [0.1 if "first" in c else 0.9 for _q, c in pairs]

    monkeypatch.setattr(rerank_mod, "_model", lambda: FakeCE())
    monkeypatch.setattr(retriever, "_cross_encoder_rerank", rerank_mod.rerank)
    out = retriever.retrieve("q", top_k=2, rerank=True)
    assert [p["url"] for p in out] == ["y", "x"]
    assert out[0]["rerank_score"] == pytest.approx(0.9)


def test_rerank_empty_does_not_load_model(monkeypatch):
    monkeypatch.setattr(rerank_mod, "_model", lambda: pytest.fail("model loaded"))
    assert rerank_mod.rerank("q", []) == []


# ---- eval metrics -----------------------------------------------------------------------------

def test_evaluate_recall_and_mrr(monkeypatch):
    import eval.evaluate as ev
    ranked = {"q1": ["u9", "u1"], "q2": ["u2"], "q3": ["u7", "u8"]}
    monkeypatch.setattr(ev, "retrieve", lambda q, top_k, rerank: [{"url": u} for u in ranked[q]][:top_k])
    queries = [{"question": "q1", "expected_urls": ["u1"]},
               {"question": "q2", "expected_urls": ["u2", "u3"]},
               {"question": "q3", "expected_urls": ["u1"]}]
    out = ev.evaluate(k=2, rerank=False, queries=queries)
    assert [r["rank"] for r in out["results"]] == [2, 1, None]
    assert out["recall_at_k"] == pytest.approx(2 / 3)
    assert out["mrr"] == pytest.approx((1 / 2 + 1) / 3)
    assert ev.evaluate(queries=[])["mrr"] == 0.0
