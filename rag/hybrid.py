def reciprocal_rank_fusion(*ranked_id_lists: list[int], k: int = 60) -> list[tuple[int, float]]:
    """Fuses several rankings (each a list of doc indices, best first) into one.

    Standard RRF: score(doc) = sum over rankings of 1 / (k + rank).
    Returns (doc_index, fused_score) pairs sorted best-first.
    """
    scores: dict[int, float] = {}
    for ranked_ids in ranked_id_lists:
        for rank, doc_id in enumerate(ranked_ids):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
