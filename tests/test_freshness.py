import os
import tempfile

import pytest

sqlite_vec = pytest.importorskip("sqlite_vec")

from ingest import ingest as ingest_module  # noqa: E402
from ingest.freshness import compute_hash  # noqa: E402
from retrieval import sqlite_store  # noqa: E402

DIM = 384


def _fake_embed_texts(texts):
    # ingest.ingest calls embed_texts(chunks); a real load isn't needed here,
    # only a vector of the right dimension for chunks_vec to accept.
    return [[float(len(t) % 7)] * DIM for t in texts]


@pytest.fixture
def db_path(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    os.remove(path)  # sqlite creates it fresh
    monkeypatch.setattr(ingest_module, "STORAGE_BACKEND", "sqlite")
    monkeypatch.setattr(ingest_module, "embed_texts", _fake_embed_texts)
    yield path
    if os.path.exists(path):
        os.remove(path)


def _chunk_contents(path, url):
    conn = sqlite_store.connect(path)
    row = conn.execute("SELECT id, content_hash FROM documents WHERE url = ?", (url,)).fetchone()
    if not row:
        conn.close()
        return None, None, []
    doc_id, content_hash = row
    chunks = [
        r[0]
        for r in conn.execute(
            "SELECT content FROM chunks WHERE document_id = ? ORDER BY chunk_index", (doc_id,)
        ).fetchall()
    ]
    conn.close()
    return doc_id, content_hash, chunks


def test_compute_hash_is_64_char_hex_and_deterministic():
    h1 = compute_hash("hello world")
    h2 = compute_hash("hello world")
    h3 = compute_hash("hello world!")
    assert len(h1) == 64
    assert all(c in "0123456789abcdef" for c in h1)
    assert h1 == h2
    assert h1 != h3


URL = "https://example.com/freshness-doc"
TEXT_V1 = "The quick brown fox jumps over the lazy dog. " * 30 + "VERSION_ONE_MARKER"
TEXT_V2 = "Something completely different about maritime safety. " * 30 + "VERSION_TWO_MARKER"


def test_new_document_stores_nonnull_content_hash(db_path):
    count = ingest_module.ingest_documents(
        [{"source": "test", "url": URL, "title": "Freshness Doc", "text": TEXT_V1}],
        sqlite_path=db_path,
    )
    doc_id, content_hash, chunks = _chunk_contents(db_path, URL)

    assert count == 1
    assert doc_id is not None
    assert content_hash is not None
    assert len(chunks) > 0


def test_reingesting_unchanged_content_is_a_noop(db_path):
    ingest_module.ingest_documents(
        [{"source": "test", "url": URL, "title": "Freshness Doc", "text": TEXT_V1}],
        sqlite_path=db_path,
    )
    doc_id_1, hash_1, chunks_1 = _chunk_contents(db_path, URL)

    count2 = ingest_module.ingest_documents(
        [{"source": "test", "url": URL, "title": "Freshness Doc", "text": TEXT_V1}],
        sqlite_path=db_path,
    )
    doc_id_2, hash_2, chunks_2 = _chunk_contents(db_path, URL)

    assert count2 == 0
    assert doc_id_2 == doc_id_1
    assert hash_2 == hash_1
    assert chunks_2 == chunks_1


def test_reingesting_changed_content_replaces_chunks_in_place(db_path):
    ingest_module.ingest_documents(
        [{"source": "test", "url": URL, "title": "Freshness Doc", "text": TEXT_V1}],
        sqlite_path=db_path,
    )
    doc_id_1, hash_1, chunks_1 = _chunk_contents(db_path, URL)

    count3 = ingest_module.ingest_documents(
        [{"source": "test", "url": URL, "title": "Freshness Doc", "text": TEXT_V2}],
        sqlite_path=db_path,
    )
    doc_id_3, hash_3, chunks_3 = _chunk_contents(db_path, URL)

    assert count3 == 1
    assert doc_id_3 == doc_id_1  # same document row, updated in place
    assert hash_3 != hash_1
    assert not any("VERSION_ONE_MARKER" in c for c in chunks_3)
    assert any("VERSION_TWO_MARKER" in c for c in chunks_3)


def test_empty_chunk_text_is_skipped_without_error(db_path):
    count = ingest_module.ingest_documents(
        [{"source": "test", "url": URL, "title": "Empty Doc", "text": "   "}],
        sqlite_path=db_path,
    )
    doc_id, _content_hash, chunks = _chunk_contents(db_path, URL)

    assert count == 0
    assert doc_id is None
    assert chunks == []
