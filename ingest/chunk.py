"""Word-window chunking with overlap. No tokenizer dependency — word count is a
close enough proxy for the chunk sizes used here."""


def chunk_text(text: str, chunk_size: int = 220, overlap: int = 40) -> list[str]:
    words = text.split()
    if not words:
        return []
    step = chunk_size - overlap
    chunks = []
    for start in range(0, len(words), step):
        piece = " ".join(words[start : start + chunk_size])
        if piece.strip():
            chunks.append(piece)
        if start + chunk_size >= len(words):
            break
    return chunks
