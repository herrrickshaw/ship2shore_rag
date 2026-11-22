"""ingest/ingest.py, ingest/backfill_regulation_refs.py, ingest/export_sqlite.py,
ingest/embed.py and db/init_db.py. The SQLite paths use a real (tiny) sqlite-vec
file; Postgres and the embedding model are faked."""

import json
import sys
import types

import pytest

pytest.importorskip("sqlite_vec")

import ingest.backfill_regulation_refs as backfill_mod  # noqa: E402
import ingest.embed as embed_mod  # noqa: E402
import ingest.export_sqlite as export_mod  # noqa: E402
import ingest.ingest as ing  # noqa: E402
from retrieval import sqlite_store  # noqa: E402

DIM = 4


@pytest.fixture
def lite(monkeypatch, tmp_path):
    """sqlite backend with a tiny vector dimension and a fake embedder."""
    monkeypatch.setattr(
        sqlite_store, "SCHEMA", sqlite_store.SCHEMA.replace("float[384]", f"float[{DIM}]")
    )
    monkeypatch.setattr(ing, "STORAGE_BACKEND", "sqlite")
    path = str(tmp_path / "corpus.sqlite3")
    monkeypatch.setattr(sqlite_store, "SQLITE_PATH", path)
    calls = []

    def fake_embed(texts):
        calls.append(list(texts))
        return [[float(len(t) % 7), 1.0, 0.0, 0.5] for t in texts]

    monkeypatch.setattr(ing, "embed_texts", fake_embed)
    return types.SimpleNamespace(path=path, embed_calls=calls)


def q(path, sql, params=()):
    conn = sqlite_store.connect(path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def doc(url="http://a", text="word " * 10, **kw):
    d = {"source": "test", "url": url, "title": "T", "text": text, "license": "L",
         "published_at": "2024-01-01"}  # fmt: skip
    d.update(kw)
    return d


# ---- ingest_documents dispatch ---------------------------------------------------


def test_ingest_documents_routes_by_backend(monkeypatch):
    monkeypatch.setattr(ing, "_ingest_sqlite", lambda d, p: ("lite", len(d), p))
    monkeypatch.setattr(ing, "_ingest_postgres", lambda d: ("pg", len(d)))
    monkeypatch.setattr(ing, "STORAGE_BACKEND", "sqlite")
    assert ing.ingest_documents([1, 2], sqlite_path="/x") == ("lite", 2, "/x")
    monkeypatch.setattr(ing, "STORAGE_BACKEND", "postgres")
    assert ing.ingest_documents([1, 2, 3]) == ("pg", 3)


# ---- sqlite ingestion --------------------------------------------------------------


def test_sqlite_ingest_inserts_document_chunks_refs_and_indexes(lite):
    text = "Under SOLAS Chapter II-2 fire safety applies. " + "word " * 300
    n = ing.ingest_documents([doc(text=text)])
    assert n == 1
    docs = q(lite.path, "SELECT source,url,title,license,published_at,content_hash FROM documents")
    assert len(docs) == 1
    assert docs[0][:5] == ("test", "http://a", "T", "L", "2024-01-01")
    from ingest.freshness import compute_hash

    assert docs[0][5] == compute_hash(text)
    chunks = q(lite.path, "SELECT chunk_index, content, regulation_refs FROM chunks ORDER BY id")
    assert len(chunks) == 2 and [c[0] for c in chunks] == [0, 1]
    assert any(r["instrument"] == "SOLAS" for r in json.loads(chunks[0][2]))
    assert json.loads(chunks[1][2]) == []
    assert q(lite.path, "SELECT count(*) FROM chunks_fts")[0][0] == 2
    assert q(lite.path, "SELECT count(*) FROM chunks_vec")[0][0] == 2


def test_sqlite_ingest_unchanged_content_is_skipped_without_embedding(lite):
    assert ing.ingest_documents([doc()]) == 1
    assert len(lite.embed_calls) == 1
    assert ing.ingest_documents([doc()]) == 0
    assert len(lite.embed_calls) == 1  # no re-embed
    assert q(lite.path, "SELECT count(*) FROM chunks")[0][0] == 1


def test_sqlite_ingest_changed_content_replaces_chunks_in_place(lite):
    ing.ingest_documents([doc(text="alpha " * 10)])
    n = ing.ingest_documents([doc(text="beta " * 10, title="New title", license="L2",
                                  published_at="2025-02-02")])  # fmt: skip
    assert n == 1
    assert q(lite.path, "SELECT count(*) FROM documents")[0][0] == 1
    row = q(lite.path, "SELECT title, license, published_at, id FROM documents")[0]
    assert row[:3] == ("New title", "L2", "2025-02-02")
    chunks = q(lite.path, "SELECT id, content FROM chunks")
    assert len(chunks) == 1 and chunks[0][1].startswith("beta")
    # stale index rows are gone, not just orphaned
    assert q(lite.path, "SELECT count(*) FROM chunks_fts")[0][0] == 1
    assert q(lite.path, "SELECT count(*) FROM chunks_vec")[0][0] == 1
    assert q(lite.path, "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'alpha'") == []
    assert len(q(lite.path, "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'beta'")) == 1


def test_sqlite_ingest_blank_text_is_skipped(lite):
    assert ing.ingest_documents([doc(text="   \n ")]) == 0
    assert lite.embed_calls == []
    assert q(lite.path, "SELECT count(*) FROM documents")[0][0] == 0


def test_sqlite_ingest_counts_each_changed_doc_and_handles_missing_optionals(lite):
    d1 = {"source": "s", "url": "u1", "title": "t1", "text": "one two"}
    d2 = doc(url="u2")
    assert ing.ingest_documents([d1, d2, d1]) == 2
    row = q(lite.path, "SELECT license, published_at FROM documents WHERE url='u1'")[0]
    assert row == (None, None)


def test_sqlite_ingest_explicit_path_overrides_default(lite, tmp_path):
    other = str(tmp_path / "other.sqlite3")
    assert ing.ingest_documents([doc()], sqlite_path=other) == 1
    assert q(other, "SELECT count(*) FROM documents")[0][0] == 1
    import os

    assert not os.path.exists(lite.path)


# ---- postgres ingestion (fake psycopg) --------------------------------------------


class PgCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        self.conn.log.append(("execute", sql, params))
        self._last = sql

    def executemany(self, sql, rows):
        self.conn.log.append(("executemany", sql, list(rows)))

    def fetchone(self):
        if self._last.startswith("SELECT id, content_hash"):
            return self.conn.existing.pop(0) if self.conn.existing else None
        return (self.conn.new_id,)


class PgConn:
    def __init__(self, existing, new_id=42):
        self.log, self.existing, self.new_id, self.commits = [], list(existing), new_id, 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return PgCursor(self)

    def commit(self):
        self.commits += 1


@pytest.fixture
def pg(monkeypatch):
    holder = types.SimpleNamespace(conn=None, dsn=None, autocommit=None)

    def connect(dsn, autocommit=None):
        holder.dsn, holder.autocommit = dsn, autocommit
        return holder.conn

    monkeypatch.setattr(ing.psycopg, "connect", connect)
    monkeypatch.setattr(
        ing, "register_vector", lambda conn: holder.__dict__.setdefault("reg", conn)
    )
    monkeypatch.setattr(ing, "embed_texts", lambda texts: [[0.1] * 3 for _ in texts])
    monkeypatch.setattr(ing, "Json", lambda v: ("JSON", v))
    monkeypatch.setattr(ing, "STORAGE_BACKEND", "postgres")
    return holder


def test_postgres_ingest_inserts_new_document(pg):
    pg.conn = PgConn(existing=[None], new_id=42)
    n = ing.ingest_documents([doc(text="Per SOLAS Chapter II-2 " + "x " * 5)])
    assert n == 1
    assert pg.autocommit is False and pg.reg is pg.conn
    assert pg.dsn == ing.DATABASE_URL
    inserts = [
        e for e in pg.conn.log if e[0] == "execute" and e[1].startswith("INSERT INTO documents")
    ]
    assert len(inserts) == 1
    assert inserts[0][2][:4] == ("test", "http://a", "T", "L") and inserts[0][2][4] == "2024-01-01"
    many = next(e for e in pg.conn.log if e[0] == "executemany")
    assert many[2][0][0] == 42 and many[2][0][1] == 0 and many[2][0][3] == [0.1] * 3
    assert many[2][0][4][0] == "JSON"
    assert pg.conn.commits == 1


def test_postgres_ingest_unchanged_is_skipped(pg):
    from ingest.freshness import compute_hash

    d = doc()
    pg.conn = PgConn(existing=[(7, compute_hash(d["text"]))])
    assert ing.ingest_documents([d]) == 0
    assert not any(e[0] == "executemany" for e in pg.conn.log)
    assert pg.conn.commits == 0


def test_postgres_ingest_changed_updates_and_replaces_chunks(pg):
    pg.conn = PgConn(existing=[(7, "stale-hash")])
    assert ing.ingest_documents([doc(title="NT", license="LL", published_at="2025-05-05")]) == 1
    sqls = [e[1].split()[0] + " " + e[1].split()[1] for e in pg.conn.log if e[0] == "execute"]
    assert "DELETE FROM" in sqls and "UPDATE documents" in sqls
    assert not any(
        e[1].startswith("INSERT INTO documents") for e in pg.conn.log if e[0] == "execute"
    )
    delete = next(e for e in pg.conn.log if e[1].startswith("DELETE FROM chunks"))
    assert delete[2] == (7,)
    update = next(e for e in pg.conn.log if e[1].startswith("UPDATE documents"))
    assert update[2][:3] == ("NT", "LL", "2025-05-05") and update[2][4] == 7
    many = next(e for e in pg.conn.log if e[0] == "executemany")
    assert many[2][0][0] == 7


def test_postgres_ingest_blank_text_skipped(pg):
    pg.conn = PgConn(existing=[None])
    assert ing.ingest_documents([doc(text="  ")]) == 0
    assert pg.conn.commits == 0


# ---- backfill ---------------------------------------------------------------------------


@pytest.fixture
def lite_refs(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sqlite_store, "SCHEMA", sqlite_store.SCHEMA.replace("float[384]", f"float[{DIM}]")
    )
    path = str(tmp_path / "bf.sqlite3")
    conn = sqlite_store.connect(path)
    sqlite_store.create_schema(conn)
    did = sqlite_store.insert_document(conn, "s", "u", "t", None)
    sqlite_store.insert_chunks(
        conn,
        did,
        [
            "Fire rules in SOLAS Chapter II-2 apply.",
            "nothing regulatory here",
            "See MARPOL Annex VI.",
        ],
        [[0.0] * DIM] * 3,
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(sqlite_store, "SQLITE_PATH", path)
    return path


def test_backfill_sqlite_sets_refs_only_where_found(monkeypatch, lite_refs):
    monkeypatch.setattr(backfill_mod, "STORAGE_BACKEND", "sqlite")
    assert backfill_mod.backfill() == 2
    rows = q(lite_refs, "SELECT content, regulation_refs FROM chunks ORDER BY id")
    refs = [json.loads(r[1]) for r in rows]
    assert refs[0][0]["instrument"] == "SOLAS"
    assert refs[1] == []
    assert refs[2][0]["instrument"] == "MARPOL"
    assert backfill_mod.backfill() == 2  # idempotent


def test_backfill_sqlite_explicit_path(monkeypatch, lite_refs, tmp_path):
    monkeypatch.setattr(backfill_mod, "STORAGE_BACKEND", "sqlite")
    monkeypatch.setattr(sqlite_store, "SQLITE_PATH", str(tmp_path / "missing.sqlite3"))
    assert backfill_mod.backfill(lite_refs) == 2


def test_backfill_postgres_updates_matching_chunks(monkeypatch):
    class Cur:
        def __init__(self, c):
            self.c = c

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=()):
            self.c.log.append((sql, params))

        def fetchall(self):
            return [(1, "SOLAS Chapter II-2 text"), (2, "plain"), (3, "MARPOL Annex I")]

    class Conn:
        def __init__(self):
            self.log, self.commits = [], 0

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def cursor(self):
            return Cur(self)

        def commit(self):
            self.commits += 1

    conn = Conn()
    psycopg = types.ModuleType("psycopg")
    psycopg.connect = lambda dsn: conn
    types_mod = types.ModuleType("psycopg.types")
    json_mod = types.ModuleType("psycopg.types.json")
    json_mod.Json = lambda v: ("J", v)
    monkeypatch.setitem(sys.modules, "psycopg", psycopg)
    monkeypatch.setitem(sys.modules, "psycopg.types", types_mod)
    monkeypatch.setitem(sys.modules, "psycopg.types.json", json_mod)
    monkeypatch.setattr(backfill_mod, "STORAGE_BACKEND", "postgres")
    assert backfill_mod.backfill() == 2
    updates = [e for e in conn.log if e[0].startswith("UPDATE chunks")]
    assert [u[1][1] for u in updates] == [1, 3]
    assert updates[0][1][0][0] == "J"
    assert conn.commits == 1


# ---- export_sqlite -----------------------------------------------------------------------


class Vec:
    def __init__(self, v):
        self.v = v

    def to_list(self):
        return self.v


class ExpPg:
    def __init__(self, docs, chunks):
        self.docs, self.chunks = docs, chunks
        self.sql = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        self.sql.append(" ".join(sql.split()))
        rows = self.docs if "FROM documents" in sql else self.chunks[params[0]]
        return types.SimpleNamespace(fetchall=lambda: rows)


class Stamp:
    def __init__(self, s):
        self.s = s

    def isoformat(self):
        return self.s


def test_export_sqlite_copies_documents_and_chunks(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sqlite_store, "SCHEMA", sqlite_store.SCHEMA.replace("float[384]", f"float[{DIM}]")
    )
    out = str(tmp_path / "snap.sqlite3")
    # a stale file at the target must be replaced, not appended to
    open(out, "w").write("garbage")
    docs = [
        (1, "arxiv", "u1", "T1", "L", Stamp("2024-01-01T00:00:00")),
        (2, "maib", "u2", "T2", None, None),
        (3, "pdf", "u3", "T3", None, None),  # no chunks -> not counted
    ]
    chunks = {
        1: [("a one", Vec([1.0, 0, 0, 0]), [{"instrument": "SOLAS"}]),
            ("a two", Vec([0, 1.0, 0, 0]), [])],
        2: [("b one", Vec([0, 0, 1.0, 0]), [])],
        3: [],
    }  # fmt: skip
    fake_pg = ExpPg(docs, chunks)
    monkeypatch.setattr(export_mod.psycopg, "connect", lambda dsn: fake_pg)
    monkeypatch.setattr(export_mod, "register_vector", lambda c: None)
    assert export_mod.export_sqlite(out) == (2, 3)
    chunk_sql = next(q for q in fake_pg.sql if "FROM chunks" in q)
    assert chunk_sql.endswith(
        "WHERE document_id = %s ORDER BY chunk_index"
    )  # ascending, so ids follow order
    rows = q(out, "SELECT url, published_at FROM documents ORDER BY id")
    assert rows == [("u1", "2024-01-01T00:00:00"), ("u2", None), ("u3", None)]
    contents = q(out, "SELECT content, chunk_index, regulation_refs FROM chunks ORDER BY id")
    assert [c[0] for c in contents] == ["a one", "a two", "b one"]
    assert [c[1] for c in contents] == [0, 1, 0]
    assert json.loads(contents[0][2]) == [{"instrument": "SOLAS"}]
    assert q(out, "SELECT count(*) FROM chunks_vec")[0][0] == 3


# ---- embed / init_db -----------------------------------------------------------------------


class FakeModel:
    def __init__(self):
        self.calls = []

    def encode(self, texts, show_progress_bar, normalize_embeddings):
        self.calls.append((list(texts), show_progress_bar, normalize_embeddings))
        return types.SimpleNamespace(tolist=lambda: [[float(len(t))] for t in texts])


def test_embed_texts_and_query(monkeypatch):
    model = FakeModel()
    embed_mod._model.cache_clear()
    monkeypatch.setattr(embed_mod, "_model", lambda: model)
    assert embed_mod.embed_texts([]) == []
    assert model.calls == []  # empty input never loads/uses the model
    assert embed_mod.embed_texts(["ab", "abc"]) == [[2.0], [3.0]]
    assert model.calls[0] == (["ab", "abc"], False, True)
    assert embed_mod.embed_query("hello") == [5.0]


def test_embed_model_is_loaded_once_with_configured_name(monkeypatch):
    created = []
    fake = types.ModuleType("sentence_transformers")
    fake.SentenceTransformer = lambda name: created.append(name) or FakeModel()
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)
    embed_mod._model.cache_clear()
    try:
        a, b = embed_mod._model(), embed_mod._model()
        assert a is b and created == [embed_mod.EMBEDDING_MODEL]
    finally:
        embed_mod._model.cache_clear()


def test_init_db_applies_both_schemas(monkeypatch, capsys):
    import db.init_db as init_db

    executed = []
    conn = types.SimpleNamespace(execute=executed.append)
    seen = {}

    class Ctx:
        def __enter__(self):
            return conn

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(init_db.psycopg, "connect", lambda dsn, autocommit: seen.update(
        dsn=dsn, autocommit=autocommit) or Ctx())  # fmt: skip
    init_db.main()
    schema = (init_db.ROOT / "db" / "schema.sql").read_text()
    ops_schema = (init_db.ROOT / "db" / "ops_schema.sql").read_text()
    assert executed == [schema, ops_schema]  # literature schema first
    assert seen == {"dsn": init_db.DATABASE_URL, "autocommit": True}
    assert capsys.readouterr().out.strip() == f"schema ready at {init_db.DATABASE_URL}"
