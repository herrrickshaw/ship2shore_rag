import json

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import ingest_service.server as service  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    # entering as a context manager runs the lifespan (starts/stops the
    # scheduler) exactly like a real deployment, rather than skipping it --
    # the interval jobs are days/hours apart so none fire during a test.
    monkeypatch.setattr(service, "RUNS_LOG_PATH", tmp_path / "ingest_runs.jsonl")
    with TestClient(service.app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "scheduler_running": True}


def test_sources_lists_every_registry_entry(client):
    resp = client.get("/sources")
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()}
    assert names == {"arxiv", "wikipedia", "maib", "ntm", "ntsb", "pdf", "file"}


def test_file_source_is_not_scheduled(client):
    sources = {s["name"]: s for s in client.get("/sources").json()}
    assert sources["file"]["scheduled"] is False
    assert sources["file"]["next_run"] is None


def test_other_sources_are_scheduled_with_a_future_next_run(client):
    sources = {s["name"]: s for s in client.get("/sources").json()}
    for name in ("arxiv", "wikipedia", "maib", "ntm", "ntsb", "pdf"):
        assert sources[name]["scheduled"] is True
        assert sources[name]["next_run"] is not None


def test_trigger_unknown_source_returns_404(client):
    resp = client.post("/sources/bogus/ingest")
    assert resp.status_code == 404


def test_trigger_known_source_runs_in_background_and_logs(client, monkeypatch, tmp_path):
    monkeypatch.setattr(service, "fetch", lambda source: [{"url": "http://x"}])
    monkeypatch.setattr(service, "ingest_documents", lambda docs: len(docs))

    resp = client.post("/sources/wikipedia/ingest")
    assert resp.status_code == 200
    assert resp.json() == {"status": "started", "source": "wikipedia"}

    # TestClient's background tasks run synchronously before the response
    # is returned to the caller (starlette's test transport), so the log
    # is already written by the time we get here.
    lines = (tmp_path / "ingest_runs.jsonl").read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["source"] == "wikipedia"
    assert record["trigger"] == "manual"
    assert record["status"] == "success"
    assert record["fetched"] == 1
    assert record["ingested"] == 1


def test_trigger_records_error_without_crashing(client, monkeypatch, tmp_path):
    def boom(source):
        raise RuntimeError("network exploded")

    monkeypatch.setattr(service, "fetch", boom)

    resp = client.post("/sources/ntsb/ingest")
    assert resp.status_code == 200  # the trigger itself always succeeds -- the run may not

    lines = (tmp_path / "ingest_runs.jsonl").read_text().splitlines()
    record = json.loads(lines[0])
    assert record["status"] == "error"
    assert "network exploded" in record["error"]


def test_runs_endpoint_reads_back_the_log(client, monkeypatch, tmp_path):
    monkeypatch.setattr(service, "fetch", lambda source: [])
    monkeypatch.setattr(service, "ingest_documents", lambda docs: 0)

    client.post("/sources/maib/ingest")
    client.post("/sources/ntm/ingest")

    resp = client.get("/runs?limit=10")
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 2
    # most recent first
    assert runs[0]["source"] == "ntm"
    assert runs[1]["source"] == "maib"


def test_runs_endpoint_empty_when_no_log_yet(client):
    resp = client.get("/runs")
    assert resp.status_code == 200
    assert resp.json() == []
