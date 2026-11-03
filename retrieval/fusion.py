"""Reciprocal Rank Fusion shared by the Postgres and SQLite retrieval backends."""

from __future__ import annotations

from typing import Sequence


def rrf_fuse(
    dense_ids: Sequence[int], sparse_ids: Sequence[int], rrf_k: int = 60
) -> dict[int, float]:
    """Fuse two best-first id rankings into {id: score}, score = sum 1/(rrf_k + rank).

    Ranks are 0-based positions; an id repeated within one list keeps its last position.
    """
    dense_rank = {cid: i for i, cid in enumerate(dense_ids)}
    sparse_rank = {cid: i for i, cid in enumerate(sparse_ids)}
    fused: dict[int, float] = {}
    for cid, rank in dense_rank.items():
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (rrf_k + rank)
    for cid, rank in sparse_rank.items():
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (rrf_k + rank)
    return fused


def top_ids(fused: dict[int, float], k: int) -> list[int]:
    """Ids of the k highest fused scores, best first."""
    return sorted(fused, key=fused.get, reverse=True)[:k]
