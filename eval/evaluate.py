"""Retrieval evaluation: Recall@k and MRR against a hand-curated query set
(eval/queries.yaml), run once with reranking on and once off, so every
retrieval-quality change (reranking, dedup, metadata filtering) has an
actual before/after number instead of a spot-check on one query.

Not RAGAS: Recall@k/MRR need no LLM judge, run offline, and directly
measure the thing retrieval-quality changes actually move — whether the
right passage got retrieved at all. LLM-judged faithfulness/answer-
relevancy is a different, later concern (generation quality, not
retrieval), worth adding only once retrieval itself isn't the bottleneck.
"""
from pathlib import Path

import yaml

from retrieval.retriever import retrieve

QUERIES_PATH = Path(__file__).parent / "queries.yaml"


def _load_queries(path: Path = QUERIES_PATH) -> list[dict]:
    return yaml.safe_load(path.read_text())


def evaluate(k: int = 5, rerank: bool = True, queries: list[dict] | None = None) -> dict:
    """Returns per-query hit rank (1-indexed, None if not found in top-k) plus
    aggregate recall@k and MRR (reciprocal rank within top-k, 0 if absent)."""
    queries = queries if queries is not None else _load_queries()
    results = []
    for q in queries:
        passages = retrieve(q["question"], top_k=k, rerank=rerank)
        expected = set(q["expected_urls"])
        rank = next((i + 1 for i, p in enumerate(passages) if p["url"] in expected), None)
        results.append({"question": q["question"], "rank": rank})

    hits = sum(1 for r in results if r["rank"] is not None)
    recall_at_k = hits / len(results) if results else 0.0
    mrr = sum(1 / r["rank"] for r in results if r["rank"] is not None) / len(results) if results else 0.0
    return {"k": k, "rerank": rerank, "recall_at_k": recall_at_k, "mrr": mrr, "results": results}


def main() -> None:
    queries = _load_queries()
    print(f"{len(queries)} queries loaded from {QUERIES_PATH.name}\n")

    for rerank in (False, True):
        summary = evaluate(rerank=rerank, queries=queries)
        label = "rerank ON " if rerank else "rerank OFF"
        print(f"[{label}] recall@{summary['k']}={summary['recall_at_k']:.2f}  MRR={summary['mrr']:.3f}")
        for r in summary["results"]:
            status = f"rank {r['rank']}" if r["rank"] else "MISS"
            print(f"    {status:>8}  {r['question']}")
        print()


if __name__ == "__main__":
    main()
