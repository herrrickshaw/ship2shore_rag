from ingest.chunk import chunk_text


def test_empty_text():
    assert chunk_text("") == []


def test_short_text_single_chunk():
    text = "word " * 50
    chunks = chunk_text(text, chunk_size=220, overlap=40)
    assert len(chunks) == 1


def test_long_text_overlaps():
    text = " ".join(f"w{i}" for i in range(500))
    chunks = chunk_text(text, chunk_size=220, overlap=40)
    assert len(chunks) > 1
    # overlap: last words of chunk[0] reappear at start of chunk[1]
    first_tail = chunks[0].split()[-5:]
    second_head = chunks[1].split()[:5]
    assert first_tail == ["w215", "w216", "w217", "w218", "w219"]
    assert second_head == ["w180", "w181", "w182", "w183", "w184"]
