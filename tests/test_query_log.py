import json
import os
import tempfile

from retrieval.query_log import log_query


def _tmp_log_path():
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    os.remove(path)  # log_query creates it fresh via append mode
    return path


def test_appends_one_json_line_with_expected_shape():
    path = _tmp_log_path()
    try:
        passages = [{"url": "http://a", "title": "T1", "score": 0.5, "rerank_score": 1.2}]
        log_query(
            "what is a bill of lading", passages, top_k=3, rerank=True, generated=False, path=path
        )

        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["question"] == "what is a bill of lading"
        assert entry["top_k"] == 3
        assert entry["rerank"] is True
        assert entry["generated"] is False
        assert entry["passages"] == [
            {"url": "http://a", "title": "T1", "score": 0.5, "rerank_score": 1.2}
        ]
        assert "timestamp" in entry
    finally:
        os.remove(path)


def test_appends_multiple_calls_as_separate_lines():
    path = _tmp_log_path()
    try:
        log_query("q1", [], top_k=5, rerank=True, generated=False, path=path)
        log_query("q2", [], top_k=5, rerank=False, generated=True, path=path)
        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["question"] == "q1"
        assert json.loads(lines[1])["question"] == "q2"
    finally:
        os.remove(path)


def test_missing_passage_fields_default_to_none_not_a_crash():
    path = _tmp_log_path()
    try:
        log_query("q", [{"url": "http://a"}], top_k=1, rerank=True, generated=False, path=path)
        with open(path) as f:
            entry = json.loads(f.readline())
        assert entry["passages"] == [
            {"url": "http://a", "title": None, "score": None, "rerank_score": None}
        ]
    finally:
        os.remove(path)


def test_unwritable_path_does_not_raise():
    # logging must never break an answer -- a bad path (e.g. a directory
    # that doesn't exist) should be swallowed, not propagate.
    log_query("q", [], top_k=1, rerank=True, generated=False, path="/nonexistent-dir/x/log.jsonl")
