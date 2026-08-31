from types import SimpleNamespace

import pytest

import cli


def test_port_question_names_the_port():
    q = cli._port_question("Strait of Hormuz")
    assert "Strait of Hormuz" in q
    assert "navigational hazards" in q
    assert "regulatory" in q


def test_ask_requires_question_or_port():
    args = SimpleNamespace(question=None, port=None)
    with pytest.raises(SystemExit):
        cli.cmd_ask(args)


def test_ask_builds_question_from_port(monkeypatch):
    captured = {}

    def fake_ask(question, **kwargs):
        captured["question"] = question
        return {"answer": None, "passages": []}

    monkeypatch.setattr(cli, "ask", fake_ask)

    args = SimpleNamespace(
        question=None,
        port="Strait of Hormuz",
        checklist=False,
        top_k=5,
        no_generate=False,
        no_rerank=False,
        since=None,
        source_filter=None,
        export=None,
    )
    cli.cmd_ask(args)
    assert "Strait of Hormuz" in captured["question"]
