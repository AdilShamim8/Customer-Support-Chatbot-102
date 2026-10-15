"""Unit tests for Reciprocal Rank Fusion."""

import pytest
from src.indexing.hybrid_index import reciprocal_rank_fusion
from src.indexing.vector_store import SearchResult


def make_results(chunk_ids: list[str], scores: list[float]) -> list[SearchResult]:
    return [
        SearchResult(
            chunk_id=cid,
            doc_id=f"doc_{i}",
            content=f"Content {i}",
            score=score,
            rank=i,
        )
        for i, (cid, score) in enumerate(zip(chunk_ids, scores))
    ]


class TestRRF:
    def test_merges_two_result_lists(self):
        list1 = make_results(["a", "b", "c"], [0.9, 0.8, 0.7])
        list2 = make_results(["c", "a", "d"], [0.95, 0.85, 0.75])

        merged = reciprocal_rank_fusion([list1, list2])
        ids = [r.chunk_id for r in merged]

        # "a" and "c" appear in both lists - should be ranked higher
        assert "a" in ids[:2] or "c" in ids[:2]

    def test_deduplicates_results(self):
        list1 = make_results(["a", "b"], [0.9, 0.8])
        list2 = make_results(["a", "c"], [0.95, 0.7])

        merged = reciprocal_rank_fusion([list1, list2])
        ids = [r.chunk_id for r in merged]

        # No duplicates
        assert len(ids) == len(set(ids))

    def test_single_list_passthrough(self):
        results = make_results(["a", "b", "c"], [0.9, 0.8, 0.7])
        merged = reciprocal_rank_fusion([results])
        assert len(merged) == len(results)

    def test_empty_lists_handled(self):
        merged = reciprocal_rank_fusion([])
        assert merged == []

    def test_weighted_fusion(self):
        list1 = make_results(["a", "b"], [0.9, 0.8])
        list2 = make_results(["b", "a"], [0.95, 0.5])

        # Heavy weight on list2 - "b" should rank higher
        merged = reciprocal_rank_fusion([list1, list2], weights=[0.2, 0.8])
        assert merged[0].chunk_id == "b"