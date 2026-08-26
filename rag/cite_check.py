"""Cross-checks a generated answer's inline [n] citation markers against the
passages actually retrieved for it. Catches two independent failure modes:
citing a passage number that doesn't exist (hallucinated numbering -- the
model inventing more sources than were actually retrieved) and citing a real
passage whose content doesn't actually support the citing sentence (weak
grounding -- a plausible-looking [n] attached to a claim the passage doesn't
back up). No LLM call: word-set Jaccard overlap on lowercased tokens is the
same "how similar is this text" family retrieval/diversify.py already uses
(SequenceMatcher.ratio() there), just simpler -- adequate for "does this
claim draw from this passage" and consistent with this project's no-LLM-
judge eval philosophy (see eval/evaluate.py's docstring).
"""

import re

CITATION_RE = re.compile(r"\[(\d+)\]")
CITATION_ONLY_RE = re.compile(r"(?:\[\d+\]\s*)+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"[a-z0-9]+")
WEAK_GROUNDING_THRESHOLD = 0.08

# Function words swamp Jaccard overlap for unrelated sentence/passage pairs
# ("the", "a", "is" match almost everything), which would mask exactly the
# hallucinated-citation case this exists to catch. Stripping them makes the
# overlap signal track actual shared content words instead.
STOPWORDS = {
    "a",
    "an",
    "the",
    "of",
    "in",
    "on",
    "at",
    "to",
    "and",
    "or",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "by",
    "for",
    "with",
    "that",
    "this",
    "it",
    "as",
    "from",
    "not",
    "no",
    "but",
    "if",
    "so",
    "than",
    "then",
    "into",
    "over",
    "under",
    "about",
    "after",
    "before",
    "during",
    "its",
    "their",
    "his",
    "her",
    "them",
    "he",
    "she",
    "they",
    "which",
    "who",
    "what",
    "when",
    "where",
    "will",
    "would",
    "can",
    "could",
    "may",
    "might",
}


def _tokenize(text: str) -> set[str]:
    return {w for w in WORD_RE.findall(text.lower()) if w not in STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _split_sentences(answer: str) -> list[str]:
    """Splits on sentence-ending punctuation, then re-merges any fragment
    that is nothing but citation markers back onto the sentence before it --
    the SYSTEM_PROMPT's "[1], [2], etc." doesn't pin markers to before or
    after the period, and a marker landing after "... fire. [1]" would
    otherwise end up detached from the claim it's citing."""
    raw = SENTENCE_SPLIT_RE.split(answer.strip())
    sentences: list[str] = []
    for chunk in raw:
        if sentences and CITATION_ONLY_RE.fullmatch(chunk.strip()):
            sentences[-1] = f"{sentences[-1]} {chunk}"
        else:
            sentences.append(chunk)
    return sentences


def check_citations(answer: str, passages: list[dict]) -> dict:
    """Checks every [n] marker in `answer` against `passages` (1-indexed,
    matching rag/pipeline.py's SYSTEM_PROMPT convention). Returns:
      valid: True iff no out-of-range citation and no weakly-grounded one
      out_of_range: sorted list of cited indices with no matching passage
      weak_grounding: [{sentence, citation_index, overlap_ratio}, ...] for
        in-range citations whose sentence barely overlaps the cited passage
      citation_count: total number of [n] markers found (including duplicates
        and out-of-range ones)
    """
    out_of_range: set[int] = set()
    weak_grounding: list[dict] = []
    citation_count = 0

    if not answer:
        return {"valid": True, "out_of_range": [], "weak_grounding": [], "citation_count": 0}

    for sentence in _split_sentences(answer):
        markers = [int(m) for m in CITATION_RE.findall(sentence)]
        if not markers:
            continue
        citation_count += len(markers)
        sentence_tokens = _tokenize(CITATION_RE.sub("", sentence))
        for idx in markers:
            if idx < 1 or idx > len(passages):
                out_of_range.add(idx)
                continue
            passage_tokens = _tokenize(passages[idx - 1]["content"])
            overlap = _jaccard(sentence_tokens, passage_tokens)
            if overlap < WEAK_GROUNDING_THRESHOLD:
                weak_grounding.append(
                    {
                        "sentence": sentence.strip(),
                        "citation_index": idx,
                        "overlap_ratio": round(overlap, 4),
                    }
                )

    return {
        "valid": not out_of_range and not weak_grounding,
        "out_of_range": sorted(out_of_range),
        "weak_grounding": weak_grounding,
        "citation_count": citation_count,
    }
