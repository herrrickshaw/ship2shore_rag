from rag.export import export, render_html, render_text

PASSAGES = [
    {
        "title": "Bill of lading",
        "url": "https://en.wikipedia.org/wiki/Bill_of_lading",
        "content": "a bill of lading is a document issued by a carrier",
        "score": 0.05,
    },
]


def test_render_html_escapes_and_includes_sources():
    html = render_html("what is a bill of lading", None, PASSAGES)
    assert "<title>what is a bill of lading</title>" in html
    assert "Bill of lading" in html
    assert "https://en.wikipedia.org/wiki/Bill_of_lading" in html


def test_render_html_uses_answer_when_present():
    html = render_html("q", "the answer", PASSAGES)
    assert "the answer" in html
    assert "Retrieved passages" not in html


def test_render_text_lists_sources():
    text = render_text("q", None, PASSAGES)
    assert "Sources:" in text
    assert "Bill of lading" in text


def test_export_infers_format_from_extension(tmp_path):
    result = {"answer": None, "passages": PASSAGES}
    out = tmp_path / "report.html"
    size = export(result, "q", str(out))
    assert size > 0
    assert out.read_text().startswith("<!doctype html>")


def test_export_unknown_format_raises(tmp_path):
    result = {"answer": None, "passages": PASSAGES}
    out = tmp_path / "report.xyz"
    try:
        export(result, "q", str(out))
        assert False, "expected ValueError"
    except ValueError:
        pass
