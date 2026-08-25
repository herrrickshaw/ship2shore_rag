import pytest

from ingest.loaders import load_file


def test_load_txt(tmp_path):
    p = tmp_path / "note.txt"
    p.write_text("ballast water must be treated before discharge")
    doc = load_file(str(p))
    assert doc["source"] == "file"
    assert "ballast water" in doc["text"]
    assert doc["title"] == "note"


def test_load_html_strips_tags(tmp_path):
    p = tmp_path / "note.html"
    p.write_text("<html><body><script>evil()</script><p>Container lashing</p></body></html>")
    doc = load_file(str(p))
    assert "Container lashing" in doc["text"]
    assert "evil" not in doc["text"]


def test_load_empty_file_returns_none(tmp_path):
    p = tmp_path / "empty.txt"
    p.write_text("   ")
    assert load_file(str(p)) is None


def test_unsupported_extension_raises(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("a,b\n1,2")
    with pytest.raises(ValueError):
        load_file(str(p))
