"""cli.py command handlers (everything except the ops sub-commands, which
tests/test_ops_cli.py covers). All I/O collaborators are faked."""

import sys
from datetime import date
from types import SimpleNamespace

import pytest

import cli


def ns(**kw):
    return SimpleNamespace(**kw)


PASSAGES = [
    {"title": "Doc A", "url": "http://a", "score": 0.5, "content": "x" * 400},
    {"title": "Doc B", "url": "http://b", "score": 0.25, "content": "short"},
]


# ---- init-db / ingest ---------------------------------------------------------


def test_cmd_init_db_delegates(monkeypatch):
    called = []
    monkeypatch.setattr(cli, "init_db", lambda: called.append(1))
    cli.cmd_init_db(ns())
    assert called == [1]


def test_cmd_ingest_passes_every_argument_and_reports_counts(monkeypatch, capsys):
    seen = {}

    def fake_fetch(source, **kw):
        seen["source"], seen["kw"] = source, kw
        return [{"url": "u1"}, {"url": "u2"}, {"url": "u3"}]

    monkeypatch.setattr(cli, "fetch_source", fake_fetch)
    monkeypatch.setattr(cli, "ingest_documents", lambda docs: len(docs) - 1)
    cli.cmd_ingest(ns(source="arxiv", query="q", max_results=7, config="c.yaml", path="p/*"))
    assert seen == {
        "source": "arxiv",
        "kw": {"query": "q", "max_results": 7, "config": "c.yaml", "path": "p/*"},
    }
    assert capsys.readouterr().out.strip() == "ingested 2 new document(s) from 3 fetched (arxiv)"


def test_cmd_ingest_converts_value_error_to_exit(monkeypatch):
    def boom(*a, **k):
        raise ValueError("bad path")

    monkeypatch.setattr(cli, "fetch_source", boom)
    monkeypatch.setattr(cli, "ingest_documents", lambda d: pytest.fail("must not ingest"))
    with pytest.raises(SystemExit) as e:
        cli.cmd_ingest(ns(source="file", query=None, max_results=1, config="c", path=None))
    assert str(e.value) == "bad path"


# ---- serve ---------------------------------------------------------------------


@pytest.fixture
def fake_uvicorn(monkeypatch):
    calls = []
    mod = SimpleNamespace(run=lambda app, host, port: calls.append((app, host, port)))
    monkeypatch.setitem(sys.modules, "uvicorn", mod)
    return calls


def test_cmd_serve_defaults(monkeypatch, fake_uvicorn, capsys):
    monkeypatch.delenv("WEBUI_HOST", raising=False)
    monkeypatch.delenv("WEBUI_PORT", raising=False)
    cli.cmd_serve(ns())
    from webui.server import app

    assert fake_uvicorn == [(app, "127.0.0.1", 8020)]
    assert "http://127.0.0.1:8020" in capsys.readouterr().out


def test_cmd_serve_env_override(monkeypatch, fake_uvicorn, capsys):
    monkeypatch.setenv("WEBUI_HOST", "0.0.0.0")
    monkeypatch.setenv("WEBUI_PORT", "9001")
    cli.cmd_serve(ns())
    assert fake_uvicorn[0][1:] == ("0.0.0.0", 9001)
    assert isinstance(fake_uvicorn[0][2], int)


def test_cmd_serve_ingest_defaults_and_override(monkeypatch, fake_uvicorn, capsys):
    monkeypatch.delenv("INGEST_SERVICE_HOST", raising=False)
    monkeypatch.delenv("INGEST_SERVICE_PORT", raising=False)
    cli.cmd_serve_ingest(ns())
    from ingest_service.server import app

    assert fake_uvicorn[-1] == (app, "127.0.0.1", 8030)
    out = capsys.readouterr().out
    assert "http://127.0.0.1:8030" in out and "POST /sources/{name}/ingest" in out
    monkeypatch.setenv("INGEST_SERVICE_HOST", "10.0.0.5")
    monkeypatch.setenv("INGEST_SERVICE_PORT", "1234")
    cli.cmd_serve_ingest(ns())
    assert fake_uvicorn[-1][1:] == ("10.0.0.5", 1234)


# ---- export-sqlite ----------------------------------------------------------------


def test_cmd_export_sqlite_default_and_explicit_output(monkeypatch, capsys):
    import config
    import ingest.export_sqlite as ex

    paths = []

    def fake_export(path):
        paths.append(path)
        return 3, 9

    monkeypatch.setattr(ex, "export_sqlite", fake_export)
    cli.cmd_export_sqlite(ns(output=None))
    cli.cmd_export_sqlite(ns(output="/tmp/custom.sqlite3"))
    assert paths == [config.SQLITE_PATH, "/tmp/custom.sqlite3"]
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"exported 3 documents / 9 chunks to {config.SQLITE_PATH}"
    assert out[1].endswith("to /tmp/custom.sqlite3")


# ---- ask --------------------------------------------------------------------------


def ask_args(**over):
    base = dict(
        question="why?", port=None, checklist=False, top_k=5, no_generate=False,
        no_rerank=False, since=None, source_filter=None, export=None, format=None,
    )  # fmt: skip
    base.update(over)
    return ns(**base)


def test_cmd_ask_maps_flags_to_pipeline_arguments(monkeypatch):
    seen = {}

    def fake_ask(question, **kw):
        seen["q"], seen["kw"] = question, kw
        return {"answer": None, "passages": []}

    monkeypatch.setattr(cli, "ask", fake_ask)
    cli.cmd_ask(
        ask_args(
            top_k=9, no_generate=True, no_rerank=True, since="2025-03-04",
            source_filter="maib", checklist=True,
        )  # fmt: skip
    )
    assert seen["q"] == "why?"
    assert seen["kw"] == {
        "top_k": 9, "generate": False, "rerank": False, "since": date(2025, 3, 4),
        "source_filter": "maib", "checklist": True,
    }  # fmt: skip
    cli.cmd_ask(ask_args())
    assert seen["kw"]["generate"] is True and seen["kw"]["rerank"] is True
    assert seen["kw"]["since"] is None


def test_cmd_ask_question_beats_port(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        cli, "ask", lambda q, **k: seen.setdefault("q", q) and {"answer": None, "passages": []}
    )
    cli.cmd_ask(ask_args(question="explicit", port="Suez"))
    assert seen["q"] == "explicit"


def test_cmd_ask_prints_answer_then_sources(monkeypatch, capsys):
    monkeypatch.setattr(cli, "ask", lambda q, **k: {"answer": "The answer.", "passages": PASSAGES})
    cli.cmd_ask(ask_args())
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "The answer."
    assert out[1] == ""
    assert out[2] == "Sources:"
    assert out[3] == "[1] Doc A (http://a) — score 0.5000"
    assert out[4] == "[2] Doc B (http://b) — score 0.2500"
    assert len(out) == 5  # extractive snippets are not printed when an answer exists


def test_cmd_ask_without_answer_prints_300_char_snippets(monkeypatch, capsys):
    monkeypatch.setattr(cli, "ask", lambda q, **k: {"answer": None, "passages": PASSAGES})
    cli.cmd_ask(ask_args())
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "Sources:"
    assert out[2] == "    " + "x" * 300 + "..."
    assert out[4] == "    short..."


def test_cmd_ask_export_writes_report(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "ask", lambda q, **k: {"answer": "Ans", "passages": PASSAGES})
    target = tmp_path / "r.txt"
    cli.cmd_ask(ask_args(export=str(target)))
    text = target.read_text()
    assert text.startswith("why?\n====\n\nAns")
    out = capsys.readouterr().out
    assert f"wrote {target} (" in out and "bytes)" in out
    html = tmp_path / "r.out"
    cli.cmd_ask(ask_args(export=str(html), format="html"))
    assert html.read_text().startswith("<!doctype html>")


# ---- hazard-brief -------------------------------------------------------------------


def test_cmd_hazard_brief_prints_refs_and_passages(monkeypatch, capsys):
    import rag.hazard_brief as hb

    seen = {}

    def fake(job, top_k, source_filter):
        seen.update(job=job, top_k=top_k, sf=source_filter)
        return {
            "job_description": job,
            "passages": PASSAGES,
            "regulation_refs": [
                {"instrument": "SOLAS", "detail": "II-2/10"},
                {"instrument": "MARPOL"},
            ],
        }

    monkeypatch.setattr(hb, "hazard_brief", fake)
    cli.cmd_hazard_brief(ns(job_description="welding", top_k=4, source_filter="ntsb", export=None))
    assert seen == {"job": "welding", "top_k": 4, "sf": "ntsb"}
    out = capsys.readouterr().out
    assert out.startswith("Hazard brief: welding\n\n")
    assert "Governing regulations (from retrieved passages):" in out
    assert "  - SOLAS II-2/10" in out
    assert "  - MARPOL\n" in out  # no detail -> no trailing space/None
    assert "Similar past incidents / relevant guidance:" in out
    assert "[1] Doc A (http://a) — score 0.5000" in out


def test_cmd_hazard_brief_without_refs_skips_section_and_exports(monkeypatch, capsys, tmp_path):
    import rag.hazard_brief as hb

    monkeypatch.setattr(
        hb,
        "hazard_brief",
        lambda *a, **k: {"job_description": "j", "passages": PASSAGES, "regulation_refs": []},
    )
    target = tmp_path / "b.md"
    cli.cmd_hazard_brief(ns(job_description="j", top_k=5, source_filter=None, export=str(target),
                            format=None))  # fmt: skip
    out = capsys.readouterr().out
    assert "Governing regulations" not in out
    assert f"wrote {target} (" in out
    body = target.read_text()
    assert body.startswith("j\n=\n")  # answer=None -> passage snippets rendered
    assert "[1] Doc A" in body


# ---- training-gaps --------------------------------------------------------------------


def test_cmd_training_gaps_empty(monkeypatch, capsys):
    import rag.training_gaps as tg

    monkeypatch.setattr(tg, "training_gaps", lambda days_ahead: [])
    cli.cmd_training_gaps(ns(days=12))
    assert capsys.readouterr().out.strip() == "no STCW certificates expiring within 12 days"


def test_cmd_training_gaps_lists_citations(monkeypatch, capsys):
    import rag.training_gaps as tg

    seen = {}

    def fake(days_ahead):
        seen["d"] = days_ahead
        return [
            {
                "id": 7, "name": "Jane", "rank": "Master", "vessel_name": "MV T",
                "stcw_cert_expiry": "2026-12-01",
                "stcw_citations": [{"title": "STCW Conv", "url": "http://stcw"}],
            }
        ]  # fmt: skip

    monkeypatch.setattr(tg, "training_gaps", fake)
    cli.cmd_training_gaps(ns(days=45))
    assert seen["d"] == 45
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("#7  Jane") and out[0].endswith("expires 2026-12-01")
    assert "MV T" in out[0]
    assert out[1] == "    cites: STCW Conv (http://stcw)"


# ---- main wiring -----------------------------------------------------------------------


def test_main_requires_a_subcommand(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cli.py"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 2


def test_main_dispatches_ingest_with_defaults(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "fetch_source", lambda s, **kw: seen.update(s=s, kw=kw) or [])
    monkeypatch.setattr(cli, "ingest_documents", lambda d: 0)
    monkeypatch.setattr(sys, "argv", ["cli.py", "ingest", "--source", "wikipedia"])
    cli.main()
    assert seen["s"] == "wikipedia"
    assert seen["kw"] == {
        "query": None, "max_results": 20, "config": "ingest/sources.yaml", "path": None,
    }  # fmt: skip


def test_main_rejects_unknown_source(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cli.py", "ingest", "--source", "nope"])
    with pytest.raises(SystemExit):
        cli.main()


def test_main_eval_and_init_db_wiring(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "run_eval", lambda: calls.append("eval"))
    monkeypatch.setattr(cli, "init_db", lambda: calls.append("init"))
    # the eval subcommand's lambda closes over cli.run_eval at parse time
    monkeypatch.setattr(sys, "argv", ["cli.py", "eval"])
    cli.main()
    monkeypatch.setattr(sys, "argv", ["cli.py", "init-db"])
    cli.main()
    assert calls == ["eval", "init"]


def test_main_ask_defaults(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "ask", lambda q, **kw: seen.update(q=q, kw=kw) or {"answer": "a",
                        "passages": []})  # fmt: skip
    monkeypatch.setattr(sys, "argv", ["cli.py", "ask", "hello"])
    cli.main()
    assert seen["q"] == "hello"
    assert seen["kw"]["top_k"] == 5 and seen["kw"]["generate"] is True
    monkeypatch.setattr(sys, "argv", ["cli.py", "ask", "--port", "Suez", "--no-generate"])
    cli.main()
    assert "Suez" in seen["q"] and seen["kw"]["generate"] is False
