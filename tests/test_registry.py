import pytest

from ingest import registry
from ingest.registry import REGISTRY, fetch


def test_registry_has_every_known_source():
    assert set(REGISTRY) == {"arxiv", "wikipedia", "maib", "ntm", "ntsb", "pdf", "file"}


def test_unknown_source_raises_value_error():
    with pytest.raises(ValueError, match="unknown source"):
        fetch("bogus")


def test_fetch_dispatches_to_the_right_plugin(monkeypatch):
    calls = []
    monkeypatch.setattr(registry, "fetch_wikipedia", lambda: calls.append("wikipedia") or [])
    fetch("wikipedia")
    assert calls == ["wikipedia"]


def test_arxiv_uses_seed_queries_when_no_query_given(monkeypatch):
    monkeypatch.setattr(registry, "fetch_arxiv_seed", lambda: [{"seed": True}])
    monkeypatch.setattr(
        registry,
        "fetch_arxiv",
        lambda q, n: (_ for _ in ()).throw(AssertionError("should not be called")),
    )
    assert fetch("arxiv", query=None, max_results=20) == [{"seed": True}]


def test_arxiv_uses_query_when_given(monkeypatch):
    calls = []
    monkeypatch.setattr(registry, "fetch_arxiv", lambda q, n: calls.append((q, n)) or [{"q": q}])
    fetch("arxiv", query="ship collision", max_results=5)
    assert calls == [("ship collision", 5)]


def test_file_source_requires_path():
    with pytest.raises(ValueError, match="--path"):
        fetch("file", path=None)


def test_file_source_dispatches_with_path(monkeypatch):
    calls = []
    monkeypatch.setattr(registry, "fetch_local_files", lambda path: calls.append(path) or [])
    fetch("file", path="./docs/**/*.pdf")
    assert calls == ["./docs/**/*.pdf"]


def test_every_plugin_has_a_description_and_interval():
    for name, plugin in REGISTRY.items():
        assert plugin.description
        assert plugin.interval_minutes >= 0
        assert plugin.name == name
