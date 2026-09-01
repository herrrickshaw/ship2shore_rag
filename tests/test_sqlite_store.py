import os
import tempfile

import pytest

sqlite_vec = pytest.importorskip("sqlite_vec")
from retrieval import sqlite_store  # noqa: E402

DIM = 8


def _fake_embedding(seed: float) -> list[float]:
    return [seed] * DIM


@pytest.fixture
def db_path(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    os.remove(path)  # sqlite creates it fresh
    monkeypatch.setattr(sqlite_store, "EMBEDDING_DIM", DIM, raising=False)
    monkeypatch.setattr(
        sqlite_store,
        "SCHEMA",
        sqlite_store.SCHEMA.replace("float[384]", f"float[{DIM}]"),
    )
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_hybrid_retrieve_ranks_keyword_and_vector_matches(db_path):
    conn = sqlite_store.connect(db_path)
    sqlite_store.create_schema(conn)

    doc_id = sqlite_store.insert_document(
        conn, "test", "https://example.com/a", "Bill of lading basics", None
    )
    sqlite_store.insert_chunks(
        conn,
        doc_id,
        ["a bill of lading is a document issued by a carrier"],
        [_fake_embedding(1.0)],
    )

    other_id = sqlite_store.insert_document(
        conn, "test", "https://example.com/b", "Unrelated topic", None
    )
    sqlite_store.insert_chunks(
        conn,
        other_id,
        ["completely unrelated content about weather patterns"],
        [_fake_embedding(-1.0)],
    )
    conn.commit()
    conn.close()

    results = sqlite_store.retrieve("bill of lading", _fake_embedding(1.0), top_k=2, path=db_path)

    assert len(results) >= 1
    assert results[0]["title"] == "Bill of lading basics"
    assert results[0]["url"] == "https://example.com/a"


@pytest.mark.parametrize(
    "query",
    [
        "what is a bill of lading?",
        'quotes " and stars * and dashes -',
        "???",
        "",
    ],
)
def test_retrieve_does_not_crash_on_fts5_special_characters(db_path, query):
    # FTS5's MATCH treats the raw string as query syntax (?, ", *, - are all
    # operators there), unlike Postgres's plainto_tsquery on the other
    # backend -- a completely normal question ending in "?" used to crash
    # this with sqlite3.OperationalError: fts5: syntax error near "?".
    conn = sqlite_store.connect(db_path)
    sqlite_store.create_schema(conn)
    doc_id = sqlite_store.insert_document(
        conn, "test", "https://example.com/a", "Bill of lading basics", None
    )
    sqlite_store.insert_chunks(
        conn,
        doc_id,
        ["a bill of lading is a document issued by a carrier"],
        [_fake_embedding(1.0)],
    )
    conn.commit()
    conn.close()

    results = sqlite_store.retrieve(query, _fake_embedding(1.0), top_k=2, path=db_path)
    assert isinstance(results, list)


def test_fts5_query_quotes_each_token():
    assert sqlite_store._fts5_query("what is a bill?") == '"what" AND "is" AND "a" AND "bill"'
    assert sqlite_store._fts5_query("???") == ""


def test_regulation_refs_round_trip(db_path):
    conn = sqlite_store.connect(db_path)
    sqlite_store.create_schema(conn)
    doc_id = sqlite_store.insert_document(
        conn, "test", "https://example.com/marpol", "MARPOL", None
    )
    refs = [{"instrument": "MARPOL", "detail": "Annex VI", "year": 1997, "raw": "MARPOL"}]
    sqlite_store.insert_chunks(
        conn, doc_id, ["MARPOL Annex VI covers air pollution"], [_fake_embedding(1.0)], [refs]
    )
    conn.commit()
    conn.close()

    results = sqlite_store.retrieve(
        "MARPOL air pollution", _fake_embedding(1.0), top_k=1, path=db_path
    )
    assert results[0]["regulation_refs"] == refs


def test_regulation_refs_defaults_to_empty_list_when_not_provided(db_path):
    conn = sqlite_store.connect(db_path)
    sqlite_store.create_schema(conn)
    doc_id = sqlite_store.insert_document(conn, "test", "https://example.com/x", "X", None)
    sqlite_store.insert_chunks(conn, doc_id, ["unrelated content here"], [_fake_embedding(1.0)])
    conn.commit()
    conn.close()

    results = sqlite_store.retrieve(
        "unrelated content", _fake_embedding(1.0), top_k=1, path=db_path
    )
    assert results[0]["regulation_refs"] == []


def test_retrieve_self_heals_a_snapshot_missing_regulation_refs(db_path):
    # Regression: retrieve() used to call connect() without create_schema(),
    # so a pre-regulation_refs snapshot -- the exact shape of the two files
    # already committed to this repo, exported before that migration
    # existed -- crashed with "no such column: c.regulation_refs" instead
    # of self-healing via create_schema()'s documented ALTER TABLE fallback.
    old_schema = sqlite_store.SCHEMA.replace(
        ",\n    regulation_refs TEXT NOT NULL DEFAULT '[]'", ""
    )
    assert "regulation_refs" not in old_schema  # sanity: the strip actually worked

    conn = sqlite_store.connect(db_path)
    conn.executescript(old_schema)
    doc_cur = conn.execute(
        "INSERT INTO documents (source, url, title, license) VALUES (?, ?, ?, ?)",
        ("test", "https://example.com/old", "Old snapshot doc", None),
    )
    doc_id = doc_cur.lastrowid
    content = "a pre-migration chunk with no regulation_refs column"
    chunk_cur = conn.execute(
        "INSERT INTO chunks (document_id, chunk_index, content) VALUES (?, ?, ?)",
        (doc_id, 0, content),
    )
    chunk_id = chunk_cur.lastrowid
    conn.execute("INSERT INTO chunks_fts (rowid, content) VALUES (?, ?)", (chunk_id, content))
    conn.execute(
        "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
        (chunk_id, sqlite_vec.serialize_float32(_fake_embedding(1.0))),
    )
    conn.commit()
    conn.close()

    results = sqlite_store.retrieve(
        "pre-migration chunk", _fake_embedding(1.0), top_k=1, path=db_path
    )
    assert results[0]["title"] == "Old snapshot doc"
    assert results[0]["regulation_refs"] == []
