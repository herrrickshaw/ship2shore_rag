"""Retrieve top-k chunks, then either generate a cited answer with Claude
(if ANTHROPIC_API_KEY is set) or return the ranked passages (extractive fallback)."""
from config import ANTHROPIC_API_KEY, MAX_CONTEXT_CHARS
from retrieval.query_log import log_query
from retrieval.retriever import retrieve

SYSTEM_PROMPT = (
    "You are a maritime shipping domain assistant. Answer ONLY using the numbered "
    "sources provided below. Cite sources inline as [1], [2], etc. If the sources "
    "don't contain the answer, say so explicitly instead of guessing."
)


def _build_context(passages: list[dict], max_chars: int = MAX_CONTEXT_CHARS) -> str:
    """Assembles numbered source blocks, stopping before max_chars rather
    than blindly concatenating every passage — nothing enforced a budget
    before this, so raising top_k had no guard against silently overflowing
    the model's context window."""
    blocks = []
    total = 0
    for i, p in enumerate(passages):
        block = f"[{i+1}] {p['title']} ({p['url']})\n{p['content']}"
        if blocks and total + len(block) > max_chars:
            print(f"context budget ({max_chars} chars) reached — dropped {len(passages) - i} of {len(passages)} passages")
            break
        blocks.append(block)
        total += len(block) + 2  # +2 for the "\n\n" join
    return "\n\n".join(blocks)


def ask(question: str, top_k: int = 5, generate: bool = True, rerank: bool = True) -> dict:
    passages = retrieve(question, top_k=top_k, rerank=rerank)
    if not passages:
        return {"answer": "No documents ingested yet — run `cli.py ingest` first.", "passages": []}

    will_generate = generate and bool(ANTHROPIC_API_KEY)
    log_query(question, passages, top_k=top_k, rerank=rerank, generated=will_generate)

    if not will_generate:
        return {"answer": None, "passages": passages}

    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    context = _build_context(passages)
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Sources:\n{context}\n\nQuestion: {question}"}],
    )
    answer = "".join(block.text for block in response.content if block.type == "text")
    return {"answer": answer, "passages": passages}
