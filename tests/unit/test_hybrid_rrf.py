from rag.hybrid import reciprocal_rank_fusion


def test_single_ranking_preserves_order():
    fused = reciprocal_rank_fusion([3, 1, 2])
    ids = [doc_id for doc_id, _ in fused]
    assert ids == [3, 1, 2]


def test_agreement_across_rankings_boosts_score():
    # doc 5 is top-ranked in both lists — should come out first.
    fused = reciprocal_rank_fusion([5, 1, 2], [5, 3, 4])
    assert fused[0][0] == 5


def test_docs_only_in_one_ranking_still_included():
    fused = reciprocal_rank_fusion([1, 2], [3])
    ids = {doc_id for doc_id, _ in fused}
    assert ids == {1, 2, 3}


def test_empty_rankings_produce_empty_result():
    assert reciprocal_rank_fusion([], []) == []
