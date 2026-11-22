"""retrieval/retriever.py (retrieve + postgres branch), retrieval/rerank.py,
rag/pipeline.py (ask, context budget, generation), eval/evaluate.py and
config.py's .env loader. Models, Postgres and Anthropic are faked."""

import sys
import types
from datetime import date

import pytest

import eval.evaluate as ev
import rag.pipeline as pipeline
import retrieval.rerank as rerank_mod
import retrieval.retriever as retriever


def P(url, source="s", content="c", published_at=None, score=0.0, title=None):
    return {"url": url, "source": source, "content": content, "published_at": published_at,
            "score": score, "title": title or url}  # fmt: skip


# ---- retrieve() orchestration --------------------------------------------------------


@pytest.fixture
def backend(monkeypatch):
    seen = {}

    def fake_pg(query, pool_k, fetch_k, rrf_k):
        seen["pg"] = (query, pool_k, fetch_k, rrf_k)
        return list(seen.get("pool", []))

    monkeypatch.setattr(retriever, "_retrieve_postgres", fake_pg)
    monkeypatch.setattr(retriever, "STORAGE_BACKEND", "postgres")
    monkeypatch.setattr(retriever, "embed_query", lambda q: [9.0])
    seen["pool"] = []
    return seen


def test_retrieve_pool_is_at_least_candidate_k(backend, monkeypatch):
    monkeypatch.setattr(retriever, "_cross_encoder_rerank", lambda q, c: c)
    retriever.retrieve("q", top_k=5)
    assert backend["pg"] == ("q", 20, 30, 60)
    retriever.retrieve("q", top_k=50, fetch_k=7, rrf_k=3)
    assert backend["pg"] == ("q", 50, 7, 3)  # top_k above candidate_k wins
    retriever.retrieve("q", top_k=5, candidate_k=8)
    assert backend["pg"][1] == 8
    retriever.retrieve("q", top_k=10, candidate_k=8)
    assert backend["pg"][1] == 10


def test_retrieve_filters_then_reranks_then_diversifies(backend, monkeypatch):
    backend["pool"] = [
        P("u1", "arxiv", "alpha one", "2020-01-01"),
        P("u2", "arxiv", "beta two", "2024-06-01"),
        P("u3", "maib", "gamma three", "2024-07-01"),
    ]
    order = []

    def fake_rerank(q, cands):
        order.append([c["url"] for c in cands])
        for c, s in zip(cands, (0.1, 0.9)):
            c["rerank_score"] = s
        return sorted(cands, key=lambda c: -c["rerank_score"])

    monkeypatch.setattr(retriever, "_cross_encoder_rerank", fake_rerank)
    out = retriever.retrieve("q", top_k=5, since=date(2024, 1, 1), source_filter="arxiv")
    assert order == [["u2"]]  # filtered pool is what the reranker sees
    assert [p["url"] for p in out] == ["u2"]


def test_retrieve_rerank_false_skips_cross_encoder(backend, monkeypatch):
    backend["pool"] = [P("u1", content="one"), P("u2", source="t", content="two")]
    monkeypatch.setattr(
        retriever, "_cross_encoder_rerank", lambda *a: pytest.fail("must not rerank")
    )
    out = retriever.retrieve("q", top_k=5, rerank=False)
    assert [p["url"] for p in out] == ["u1", "u2"]


def test_retrieve_applies_diversify_cut(backend, monkeypatch):
    texts = ["anchor chain failure", "bridge watch handover", "fire in engine room",
             "ballast water exchange", "mooring line snap-back", "cargo hold ventilation"]  # fmt: skip
    backend["pool"] = [P(f"u{i}", source=f"s{i}", content=t) for i, t in enumerate(texts)]
    out = retriever.retrieve("q", top_k=2, rerank=False)
    assert [p["url"] for p in out] == ["u0", "u1"]
    # a near-duplicate of the first hit is skipped, not counted toward top_k
    backend["pool"][1]["content"] = "anchor chain failure."
    out = retriever.retrieve("q", top_k=2, rerank=False)
    assert [p["url"] for p in out] == ["u0", "u2"]


def test_retrieve_sqlite_backend_dispatch(monkeypatch):
    from retrieval import sqlite_store

    seen = {}
    monkeypatch.setattr(retriever, "STORAGE_BACKEND", "sqlite")
    monkeypatch.setattr(retriever, "embed_query", lambda q: [1.0, 2.0])
    monkeypatch.setattr(
        sqlite_store, "retrieve",
        lambda *a: seen.setdefault("a", a) and [P("u1", content="hello")],
    )  # fmt: skip
    monkeypatch.setattr(
        retriever, "_retrieve_postgres", lambda *a: pytest.fail("wrong backend")
    )
    out = retriever.retrieve("query", top_k=3, fetch_k=11, rrf_k=5, rerank=False)
    assert seen["a"] == ("query", [1.0, 2.0], 20, 11, 5)
    assert [p["url"] for p in out] == ["u1"]


def test_passage_date_with_trailing_z_and_offsets():
    assert retriever._passage_date("2024-03-15T23:59:59+00:00") == date(2024, 3, 15)
    assert retriever._passage_date("2024-03-15T00:00:00Z") == date(2024, 3, 15)
    with pytest.raises(ValueError):
        retriever._passage_date("not a date")


def test_apply_filters_since_is_inclusive_and_undated_excluded():
    ps = [
        P("old", published_at="2023-12-31"),
        P("edge", published_at="2024-01-01"),
        P("new", published_at="2024-01-02"),
        P("undated", published_at=None),
    ]
    out = retriever._apply_filters(ps, since=date(2024, 1, 1), source_filter=None)
    assert [p["url"] for p in out] == ["edge", "new"]
    # no since -> undated kept
    assert len(retriever._apply_filters(ps, since=None, source_filter=None)) == 4


# ---- _retrieve_postgres (fake psycopg) --------------------------------------------------


class Cur:
    def __init__(self, script):
        self.script = script
        self.log = []
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        self.log.append((" ".join(sql.split()), params))
        if "ORDER BY embedding" in sql:
            self._rows = self.script["dense"]
        elif "plainto_tsquery" in sql:
            self._rows = self.script["sparse"]
        elif "ANY(" in sql:
            self._rows = self.script["rows"]
        else:
            self._rows = []

    def fetchall(self):
        return self._rows


class Conn:
    def __init__(self, cur):
        self.cur = cur

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self.cur


def run_pg(monkeypatch, script, top_k=3, fetch_k=30, rrf_k=60):
    cur = Cur(script)
    monkeypatch.setattr(retriever.psycopg, "connect", lambda dsn: Conn(cur))
    monkeypatch.setattr(retriever, "register_vector", lambda c: None)
    monkeypatch.setattr(retriever, "Vector", lambda v: ("VEC", tuple(v)))
    monkeypatch.setattr(retriever, "embed_query", lambda q: [0.5, 0.25])
    return retriever._retrieve_postgres("the query", top_k, fetch_k, rrf_k), cur


def row(i):
    return (i, f"content {i}", f"title {i}", f"url{i}", "src", None, [{"instrument": "X"}])


def test_postgres_retrieval_fuses_dense_and_sparse_with_rrf(monkeypatch):
    # chunk 2 is rank 1 (dense) and rank 0 (sparse) -> highest fused score
    script = {"dense": [(1,), (2,), (3,)], "sparse": [(2,), (4,)], "rows": [row(i) for i in (1, 2, 3, 4)]}
    out, cur = run_pg(monkeypatch, script, top_k=3, rrf_k=60)
    assert [p["url"] for p in out] == ["url2", "url1", "url4"]
    assert out[0]["score"] == pytest.approx(1 / 61 + 1 / 60)
    assert out[1]["score"] == pytest.approx(1 / 60)
    assert out[2]["score"] == pytest.approx(1 / 61)
    assert out[0]["regulation_refs"] == [{"instrument": "X"}] and out[0]["source"] == "src"
    sqls = [s for s, _ in cur.log]
    assert sqls[0] == "SET LOCAL ivfflat.probes = 10"
    assert cur.log[1][1] == (("VEC", (0.5, 0.25)), 30)
    assert cur.log[2][1] == ("the query", "the query", 30)
    assert cur.log[3][1] == ([2, 1, 4],)


def test_postgres_retrieval_empty_returns_no_passages(monkeypatch):
    out, cur = run_pg(monkeypatch, {"dense": [], "sparse": [], "rows": []})
    assert out == []
    assert not any("ANY(" in s for s, _ in cur.log)  # no join query when nothing matched


def test_postgres_retrieval_drops_ids_missing_from_join(monkeypatch):
    script = {"dense": [(1,), (2,)], "sparse": [], "rows": [row(2)]}
    out, _ = run_pg(monkeypatch, script, top_k=5)
    assert [p["url"] for p in out] == ["url2"]


# ---- rerank ----------------------------------------------------------------------------------


def test_rerank_empty_does_not_load_model(monkeypatch):
    monkeypatch.setattr(rerank_mod, "_model", lambda: pytest.fail("model must not load"))
    assert rerank_mod.rerank("q", []) == []


def test_rerank_scores_sorts_descending_and_keeps_all(monkeypatch):
    pairs = []

    class M:
        def predict(self, p):
            pairs.extend(p)
            return [0.2, 0.9, 0.5]

    monkeypatch.setattr(rerank_mod, "_model", lambda: M())
    ps = [P("a", content="ca"), P("b", content="cb"), P("c", content="cc")]
    out = rerank_mod.rerank("question", ps)
    assert pairs == [("question", "ca"), ("question", "cb"), ("question", "cc")]
    assert [p["url"] for p in out] == ["b", "c", "a"]
    assert [p["rerank_score"] for p in out] == [0.9, 0.5, 0.2]
    assert all(isinstance(p["rerank_score"], float) for p in out)


def test_rerank_model_is_cached_and_uses_configured_name(monkeypatch):
    made = []
    fake = types.ModuleType("sentence_transformers")
    fake.CrossEncoder = lambda name: made.append(name) or object()
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)
    rerank_mod._model.cache_clear()
    try:
        assert rerank_mod._model() is rerank_mod._model()
        assert made == [rerank_mod.RERANKER_MODEL]
    finally:
        rerank_mod._model.cache_clear()


# ---- pipeline ----------------------------------------------------------------------------------


@pytest.fixture
def pipe(monkeypatch):
    state = types.SimpleNamespace(retrieve_kw=None, logged=[], passages=[P("u1", content="body1"),
                                                                          P("u2", content="body2")])  # fmt: skip

    def fake_retrieve(q, **kw):
        state.retrieve_kw = (q, kw)
        return state.passages

    monkeypatch.setattr(pipeline, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        pipeline, "log_query", lambda q, ps, **kw: state.logged.append((q, ps, kw))
    )
    return state


def fake_anthropic(monkeypatch, text_blocks=("Answer [1].",), record=None):
    record = record if record is not None else {}

    class Block:
        def __init__(self, t, type_="text"):
            self.text, self.type = t, type_

    class Messages:
        def create(self, **kw):
            record["create"] = kw
            blocks = [Block(t) for t in text_blocks] + [Block("tool", "tool_use")]
            return types.SimpleNamespace(content=blocks)

    class Client:
        def __init__(self, api_key):
            record["key"] = api_key
            self.messages = Messages()

    mod = types.ModuleType("anthropic")
    mod.Anthropic = Client
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    return record


def test_ask_passes_retrieval_arguments(pipe, monkeypatch):
    monkeypatch.setattr(pipeline, "ANTHROPIC_API_KEY", "")
    since = date(2024, 1, 1)
    pipeline.ask("q?", top_k=7, rerank=False, since=since, source_filter="maib")
    assert pipe.retrieve_kw == (
        "q?", {"top_k": 7, "rerank": False, "since": since, "source_filter": "maib"}
    )  # fmt: skip


def test_ask_without_key_returns_extractive_passages_and_logs(pipe, monkeypatch):
    monkeypatch.setattr(pipeline, "ANTHROPIC_API_KEY", "")
    out = pipeline.ask("q?", top_k=4, rerank=False)
    assert out == {"answer": None, "passages": pipe.passages}
    assert pipe.logged == [("q?", pipe.passages, {"top_k": 4, "rerank": False, "generated": False})]


def test_ask_generate_false_never_calls_model_even_with_key(pipe, monkeypatch):
    monkeypatch.setattr(pipeline, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setitem(sys.modules, "anthropic", None)  # import would raise
    out = pipeline.ask("q?", generate=False)
    assert out["answer"] is None
    assert pipe.logged[0][2]["generated"] is False


def test_ask_generates_cited_answer(pipe, monkeypatch):
    monkeypatch.setattr(pipeline, "ANTHROPIC_API_KEY", "sk-test")
    rec = fake_anthropic(monkeypatch, text_blocks=("Part one. ", "Part two."))
    out = pipeline.ask("What is X?")
    assert out["answer"] == "Part one. Part two."  # non-text blocks ignored
    assert out["passages"] == pipe.passages
    kw = rec["create"]
    assert rec["key"] == "sk-test" and kw["max_tokens"] == 1024
    assert kw["system"] == pipeline.SYSTEM_PROMPT
    content = kw["messages"][0]["content"]
    assert content.startswith("Sources:\n[1] u1 (u1)\nbody1\n\n[2] u2 (u2)\nbody2")
    assert content.endswith("\n\nQuestion: What is X?")
    assert pipe.logged[0][2]["generated"] is True


def test_ask_checklist_flag_selects_checklist_prompt(pipe, monkeypatch):
    monkeypatch.setattr(pipeline, "ANTHROPIC_API_KEY", "sk-test")
    rec = fake_anthropic(monkeypatch)
    pipeline.ask("q", checklist=True)
    assert rec["create"]["system"] == pipeline.CHECKLIST_SYSTEM_PROMPT


def test_ask_no_passages_does_not_log(pipe, monkeypatch):
    pipe.passages = []
    monkeypatch.setattr(pipeline, "ANTHROPIC_API_KEY", "sk-test")
    out = pipeline.ask("q")
    assert out["passages"] == [] and "ingest" in out["answer"]
    assert pipe.logged == []


def test_build_context_numbers_sources_and_joins_with_blank_line():
    ps = [P("u1", content="aa", title="T1"), P("u2", content="bb", title="T2")]
    assert pipeline._build_context(ps) == "[1] T1 (u1)\naa\n\n[2] T2 (u2)\nbb"
    assert pipeline._build_context([]) == ""


def test_build_context_budget_boundary(capsys):
    ps = [P(f"u{i}", content="x" * 10, title="T") for i in range(3)]
    block = len("[1] T (u0)\n" + "x" * 10)  # 21 chars
    # two blocks fit exactly: total after first = block+2, second needs block+2+block <= max
    exact = block + 2 + block
    out = pipeline._build_context(ps, max_chars=exact)
    assert out.count("[") == 2 and "[3]" not in out
    assert "dropped 1 of 3 passages" in capsys.readouterr().out
    out = pipeline._build_context(ps, max_chars=exact - 1)
    assert out.count("[") == 1
    assert "dropped 2 of 3 passages" in capsys.readouterr().out
    out = pipeline._build_context(ps, max_chars=exact * 3)
    assert out.count("[") == 3 and capsys.readouterr().out == ""


def test_build_context_always_keeps_first_passage_even_if_oversize():
    ps = [P("u1", content="x" * 500), P("u2", content="y")]
    out = pipeline._build_context(ps, max_chars=10)
    assert "[1]" in out and "[2]" not in out


# ---- eval ---------------------------------------------------------------------------------------


def test_evaluate_computes_recall_and_mrr(monkeypatch):
    results = {
        "q1": [P("x"), P("hit1")],
        "q2": [P("hit2")],
        "q3": [P("nope")],
        "q4": [P("a"), P("b"), P("hit4")],
    }
    seen = []

    def fake_retrieve(question, top_k, rerank):
        seen.append((question, top_k, rerank))
        return results[question]

    monkeypatch.setattr(ev, "retrieve", fake_retrieve)
    queries = [
        {"question": "q1", "expected_urls": ["hit1", "other"]},
        {"question": "q2", "expected_urls": ["hit2"]},
        {"question": "q3", "expected_urls": ["hit3"]},
        {"question": "q4", "expected_urls": ["hit4"]},
    ]
    out = ev.evaluate(k=3, rerank=False, queries=queries)
    assert seen[0] == ("q1", 3, False)
    assert [r["rank"] for r in out["results"]] == [2, 1, None, 3]
    assert out["recall_at_k"] == pytest.approx(3 / 4)
    assert out["mrr"] == pytest.approx((1 / 2 + 1 + 0 + 1 / 3) / 4)
    assert (out["k"], out["rerank"]) == (3, False)


def test_evaluate_empty_queries_gives_zeroes(monkeypatch):
    monkeypatch.setattr(ev, "retrieve", lambda *a, **k: pytest.fail("no queries"))
    out = ev.evaluate(queries=[])
    assert (out["recall_at_k"], out["mrr"], out["results"]) == (0.0, 0.0, [])
    assert (out["k"], out["rerank"]) == (5, True)


def test_evaluate_defaults_to_queries_yaml(monkeypatch):
    monkeypatch.setattr(ev, "retrieve", lambda *a, **k: [])
    out = ev.evaluate()
    assert len(out["results"]) == len(ev._load_queries()) > 0
    assert out["recall_at_k"] == 0.0


def test_load_queries_reads_given_path(tmp_path):
    f = tmp_path / "q.yaml"
    f.write_text("- question: hi\n  expected_urls: [u]\n")
    assert ev._load_queries(f) == [{"question": "hi", "expected_urls": ["u"]}]


def test_eval_main_prints_both_modes(monkeypatch, capsys):
    calls = []

    def fake_eval(k=5, rerank=True, queries=None):
        calls.append(rerank)
        return {"k": 5, "recall_at_k": 0.5, "mrr": 0.25,
                "results": [{"question": "hit q", "rank": 2}, {"question": "miss q", "rank": None}]}  # fmt: skip

    monkeypatch.setattr(ev, "evaluate", fake_eval)
    monkeypatch.setattr(ev, "_load_queries", lambda: [1, 2])
    ev.main()
    out = capsys.readouterr().out
    assert calls == [False, True]  # off first, then on
    assert out.startswith("2 queries loaded from queries.yaml\n")
    assert "[rerank OFF] recall@5=0.50  MRR=0.250" in out
    assert "[rerank ON ] recall@5=0.50  MRR=0.250" in out
    assert "rank 2  hit q" in out and "MISS  miss q" in out


# ---- config .env loader ----------------------------------------------------------------------


def test_load_dotenv_parses_and_never_overrides(monkeypatch, tmp_path):
    import config

    env = tmp_path / ".env"
    env.write_text(
        "# comment\n\nFOO_T=bar\n  SPACED = value with = sign \nNOEQ\nEXISTING_T=fromfile\n"
    )
    monkeypatch.delenv("FOO_T", raising=False)
    monkeypatch.delenv("SPACED", raising=False)
    monkeypatch.setenv("EXISTING_T", "fromenv")
    config._load_dotenv(env)
    import os

    assert os.environ["FOO_T"] == "bar"
    assert os.environ["SPACED"] == "value with = sign"
    assert os.environ["EXISTING_T"] == "fromenv"
    assert "NOEQ" not in os.environ
    monkeypatch.delenv("FOO_T")
    monkeypatch.delenv("SPACED")
    config._load_dotenv(tmp_path / "missing.env")  # absent file is a no-op
    assert "FOO_T" not in os.environ


def test_config_defaults_are_sane():
    import config

    assert config.EMBEDDING_DIM == 384
    assert config.MAX_CONTEXT_CHARS > 0
    assert config.STORAGE_BACKEND in {"postgres", "sqlite"}
