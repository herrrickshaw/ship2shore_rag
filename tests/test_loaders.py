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


def test_load_xlsx(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    p = tmp_path / "fleet.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Vessels"
    ws.append(["Name", "Type"])
    ws.append(["Baylor J. Tregre", "Towing vessel"])
    wb.save(p)

    doc = load_file(str(p))
    assert "Vessels" in doc["text"]
    assert "Baylor J. Tregre" in doc["text"]


def test_load_pptx(tmp_path):
    pptx = pytest.importorskip("pptx")
    p = tmp_path / "briefing.pptx"
    prs = pptx.Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Casualty Briefing"
    prs.save(p)

    doc = load_file(str(p))
    assert "Casualty Briefing" in doc["text"]
