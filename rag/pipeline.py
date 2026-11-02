"""Retrieve top-k chunks, then either generate a cited answer with Claude
(if ANTHROPIC_API_KEY is set) or return the ranked passages (extractive fallback)."""

from __future__ import annotations

from datetime import date
from typing import Callable, Protocol

from config import ANTHROPIC_API_KEY, MAX_CONTEXT_CHARS
from retrieval.query_log import log_query
from retrieval.retriever import retrieve

SYSTEM_PROMPT = (
    "You are a maritime shipping domain assistant. Answer ONLY using the numbered "
    "sources provided below. Cite sources inline as [1], [2], etc. If the sources "
    "don't contain the answer, say so explicitly instead of guessing."
)

CHECKLIST_SYSTEM_PROMPT = (
    "You are a maritime shipping domain assistant. Using ONLY the numbered sources "
    "provided below, produce an ordered, numbered checklist of concrete steps that "
    "answers the question -- the shape a watchkeeper needs, not a prose paragraph. "
    "Cite the source for each step inline as [1], [2], etc. If the sources don't "
    "contain enough to build a checklist, say so explicitly instead of guessing."
)

GENERATION_MODEL = "claude-sonnet-5"
GENERATION_MAX_TOKENS = 1024


class AnswerGenerator(Protocol):
    """Turns (system prompt, user message) into answer text; the LLM seam."""

    def __call__(self, system: str, user: str) -> str: ...


def anthropic_generator(api_key: str) -> AnswerGenerator:
    """Default generator: one Claude messages.create call (anthropic imported lazily)."""

    def generate(system: str, user: str) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=GENERATION_MODEL,
            max_tokens=GENERATION_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    return generate


def _system_prompt(checklist: bool) -> str:
    return CHECKLIST_SYSTEM_PROMPT if checklist else SYSTEM_PROMPT


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
            print(
                f"context budget ({max_chars} chars) reached — dropped {len(passages) - i} of {len(passages)} passages"
            )
            break
        blocks.append(block)
        total += len(block) + 2  # +2 for the "\n\n" join
    return "\n\n".join(blocks)


def ask(
    question: str,
    top_k: int = 5,
    generate: bool = True,
    rerank: bool = True,
    since: date | None = None,
    source_filter: str | None = None,
    checklist: bool = False,
    generator: AnswerGenerator | None = None,
    retriever: Callable[..., list[dict]] | None = None,
) -> dict:
    """Answer a question from retrieved passages.

    generator/retriever are injection seams; by default generation uses Claude when
    ANTHROPIC_API_KEY is set (else extractive passages only) and retrieval uses
    retrieval.retriever.retrieve. An injected generator is used whenever generate=True.
    """
    passages = (retriever or retrieve)(
        question, top_k=top_k, rerank=rerank, since=since, source_filter=source_filter
    )
    if not passages:
        return {"answer": "No documents ingested yet — run `cli.py ingest` first.", "passages": []}

    if generator is None and ANTHROPIC_API_KEY:
        generator = anthropic_generator(ANTHROPIC_API_KEY)
    will_generate = generate and generator is not None
    log_query(question, passages, top_k=top_k, rerank=rerank, generated=will_generate)

    if not will_generate:
        return {"answer": None, "passages": passages}

    context = _build_context(passages)
    answer = generator(_system_prompt(checklist), f"Sources:\n{context}\n\nQuestion: {question}")
    return {"answer": answer, "passages": passages}
