"""Remaining edge branches: loaders (pdf/docx/pptx notes/glob), registry
adapters, cite-check tokenization, CFR dedupe, ingest-service log failure,
empty sqlite retrieval and the Postgres side of ops.store._Conn."""

import types

import pytest

from ingest import loaders, registry
from ingest.loaders import fetch_local_files, load_file
from ingest.regulation_refs import extract_refs

# ---- loaders -------------------------------------------------------------------------


def test_load_pdf_joins_pages_and_strips_nul(monkeypatch, tmp_path):
    class Page:
        def __init__(self, t):
            self.t = t

        def extract_text(self):
            return self.t

    monkeypatch.setattr(
        loaders, "PdfReader", lambda path: types.SimpleNamespace(pages=[Page("a\x00b"), Page(None), Page("c")])
    )
    p = tmp_path / "x.PDF"  # extension match is case-insensitive
    p.write_bytes(b"%PDF")
    doc = load_file(str(p))
    assert doc["text"] == "ab\n\nc"
    assert doc["source"] == "file" and doc["title"] == "x"
    assert doc["url"] == f"file://{p.resolve()}"
    assert doc["license"].startswith("local file")


def test_load_docx(tmp_path):
    docx = pytest.importorskip("docx")
    p = tmp_path / "w.docx"
    d = docx.Document()
    d.add_paragraph("First para")
    d.add_paragraph("Second para")
    d.save(p)
    assert load_file(str(p))["text"] == "First para\nSecond para"


def test_load_pptx_includes_notes_and_skips_blank_shapes(tmp_path):
    pptx = pytest.importorskip("pptx")
    p = tmp_path / "n.pptx"
    prs = pptx.Presentation()
    s1 = prs.slides.add_slide(prs.slide_layouts[1])
    s1.shapes.title.text = "Title One"
    s1.notes_slide.notes_text_frame.text = "speaker words"
    s2 = prs.slides.add_slide(prs.slide_layouts[5])
    s2.shapes.title.text = "  "
    prs.save(p)
    lines = load_file(str(p))["text"].splitlines()
    assert lines == ["# Slide 1", "Title One", "(notes) speaker words", "# Slide 2"]


def test_load_xlsx_skips_empty_rows_and_none_cells(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    p = tmp_path / "s.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "A"
    ws.append(["x", None, 3])
    ws.append([None, None])
    wb.create_sheet("B").append(["y"])
    wb.save(p)
    assert load_file(str(p))["text"] == "# A\nx\t3\n# B\ny"


def test_html_loader_drops_script_and_style(tmp_path):
    p = tmp_path / "p.htm"
    p.write_text("<html><style>.a{}</style><script>var x=1</script><p>Hello</p><p>World</p></html>")
    text = load_file(str(p))["text"]
    assert "Hello" in text and "World" in text and "var x" not in text and ".a{}" not in text


def test_fetch_local_files_glob_sorting_and_failure_isolation(tmp_path, capsys):
    (tmp_path / "b.txt").write_text("bee")
    (tmp_path / "a.md").write_text("aye")
    (tmp_path / "empty.txt").write_text("   ")
    (tmp_path / "bad.pdf").write_bytes(b"not a pdf")
    (tmp_path / "ignored.xyz").write_text("zzz")
    (tmp_path / "sub.txt").mkdir()  # a directory matching the glob is skipped
    docs = fetch_local_files(str(tmp_path / "*"))
    assert [d["title"] for d in docs] == ["a", "b"]  # sorted; empty/unsupported/bad dropped
    out = capsys.readouterr().out
    assert "skipping" in out and "bad.pdf" in out and "ignored.xyz" in out
    assert fetch_local_files(str(tmp_path / "*.nothing")) == []


def test_fetch_local_files_recursive(tmp_path):
    (tmp_path / "d1" / "d2").mkdir(parents=True)
    (tmp_path / "d1" / "d2" / "deep.txt").write_text("deep")
    docs = fetch_local_files(str(tmp_path / "**" / "*.txt"))
    assert [d["title"] for d in docs] == ["deep"]


# ---- registry adapters ----------------------------------------------------------------


def test_registry_adapters_forward_only_their_arguments(monkeypatch):
    seen = {}
    monkeypatch.setattr(registry, "fetch_maib", lambda n: seen.update(maib=n) or ["m"])
    monkeypatch.setattr(registry, "fetch_ntm", lambda n: seen.update(ntm=n) or ["n"])
    monkeypatch.setattr(registry, "fetch_ntsb", lambda n: seen.update(ntsb=n) or ["s"])
    monkeypatch.setattr(registry, "fetch_pdf_sources", lambda c: seen.update(pdf=c) or ["p"])
    monkeypatch.setattr(registry, "fetch_wikipedia", lambda: ["w"])
    assert registry.fetch("maib", max_results=3, query="ignored") == ["m"]
    assert registry.fetch("ntm", max_results=4) == ["n"]
    assert registry.fetch("ntsb", max_results=5) == ["s"]
    assert registry.fetch("pdf", config="c.yaml") == ["p"]
    assert registry.fetch("wikipedia", max_results=1) == ["w"]
    assert seen == {"maib": 3, "ntm": 4, "ntsb": 5, "pdf": "c.yaml"}


def test_registry_adapter_defaults(monkeypatch):
    seen = {}
    monkeypatch.setattr(registry, "fetch_maib", lambda n: seen.update(maib=n) or [])
    monkeypatch.setattr(registry, "fetch_ntm", lambda n: seen.update(ntm=n) or [])
    monkeypatch.setattr(registry, "fetch_ntsb", lambda n: seen.update(ntsb=n) or [])
    monkeypatch.setattr(registry, "fetch_pdf_sources", lambda c: seen.update(pdf=c) or [])
    for name in ("maib", "ntm", "ntsb", "pdf"):
        registry.fetch(name)
    assert seen == {"maib": 30, "ntm": 10, "ntsb": 30, "pdf": "ingest/sources.yaml"}


def test_registry_file_source_flags_and_intervals():
    assert registry.REGISTRY["file"].needs_path is True
    assert registry.REGISTRY["file"].interval_minutes == 0
    assert all(not p.needs_path for n, p in registry.REGISTRY.items() if n != "file")
    assert registry.REGISTRY["wikipedia"].interval_minutes == 10080
    assert registry.REGISTRY["arxiv"].interval_minutes == 1440
    with pytest.raises(ValueError, match="unknown source: 'nope'"):
        registry.fetch("nope")


# ---- cite_check / regulation_refs ---------------------------------------------------------


def test_jaccard_edges():
    from rag.cite_check import _jaccard

    assert _jaccard(set(), {"a"}) == 0.0
    assert _jaccard({"a"}, set()) == 0.0
    assert _jaccard(set(), set()) == 0.0
    assert _jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)
    assert _jaccard({"a"}, {"a"}) == 1.0


def test_extract_refs_dedupes_repeated_cfr_citation():
    refs = extract_refs("See 46 CFR 4.05 and again 46 CFR 4.05, plus 33 CFR 160.")
    cfr = [r for r in refs if r["instrument"] == "CFR"]
    assert [r["detail"] for r in cfr] == ["46 CFR 4.05", "33 CFR 160"]
    assert all(r["year"] is None for r in cfr)


# ---- ingest service log failure -------------------------------------------------------------


def test_run_ingest_survives_unwritable_runs_log(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("apscheduler")
    import ingest_service.server as svc

    monkeypatch.setattr(svc, "RUNS_LOG_PATH", tmp_path / "no_such_dir" / "runs.jsonl")
    monkeypatch.setattr(svc, "fetch", lambda s: [{"url": "u"}])
    monkeypatch.setattr(svc, "ingest_documents", lambda d: 1)
    svc._run_ingest("wikipedia", "manual")  # must not raise


# ---- sqlite_store empty corpus -----------------------------------------------------------------


def test_sqlite_retrieve_on_empty_store_returns_nothing(monkeypatch, tmp_path):
    pytest.importorskip("sqlite_vec")
    from retrieval import sqlite_store

    monkeypatch.setattr(sqlite_store, "SCHEMA", sqlite_store.SCHEMA.replace("float[384]", "float[4]"))
    path = str(tmp_path / "e.sqlite3")
    assert sqlite_store.retrieve("anything at all?", [0.0] * 4, path=path) == []


def test_fts5_query_quotes_every_word():
    from retrieval.sqlite_store import _fts5_query

    assert _fts5_query('what is "port state" control?') == '"what" AND "is" AND "port" AND "state" AND "control"'
    assert _fts5_query("??!") == ""


# ---- ops.store postgres plumbing ------------------------------------------------------------------


class PgCur:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


def test_store_rows_and_row_helpers_by_backend():
    from ops import store

    assert store._rows(PgCur([{"a": 1}]), "postgres") == [{"a": 1}]
    assert store._row(PgCur([{"a": 1}]), "postgres") == {"a": 1}
    assert store._row(PgCur([]), "postgres") is None
    assert store._row(PgCur([]), "sqlite") is None


def test_store_conn_uses_pg_dialect_and_commits_only_on_success(monkeypatch):
    from ops import store

    log = []

    class Raw:
        def execute(self, sql, params):
            log.append(("exec", sql, params))
            return "cursor"

        def commit(self):
            log.append("commit")

        def close(self):
            log.append("close")

    monkeypatch.setattr(store, "STORAGE_BACKEND", "postgres")
    monkeypatch.setattr(store.psycopg, "connect", lambda dsn, row_factory: Raw())
    with store._Conn() as c:
        assert c.backend == "postgres"
        assert c.execute("PG %s", "LITE ?", (1,)) == "cursor"
    assert log == [("exec", "PG %s", (1,)), "commit", "close"]
    log.clear()
    with pytest.raises(RuntimeError):
        with store._Conn() as c:
            raise RuntimeError("boom")
    assert log == ["close"]  # rolled back by never committing
