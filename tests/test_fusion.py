import pytest

from retrieval.fusion import rrf_fuse, top_ids


def test_rrf_fuse_sums_reciprocal_ranks():
    fused = rrf_fuse([1, 2], [2, 3], rrf_k=60)
    assert fused[1] == pytest.approx(1 / 60)
    assert fused[2] == pytest.approx(1 / 61 + 1 / 60)
    assert fused[3] == pytest.approx(1 / 61)


def test_rrf_fuse_empty():
    assert rrf_fuse([], []) == {}


def test_rrf_fuse_duplicate_id_keeps_last_position():
    # characterises the original dict-comprehension behaviour
    assert rrf_fuse([7, 8, 7], [], rrf_k=10) == {7: pytest.approx(1 / 12), 8: pytest.approx(1 / 11)}


def test_top_ids_orders_best_first_and_cuts():
    assert top_ids({1: 0.1, 2: 0.5, 3: 0.3}, 2) == [2, 3]
