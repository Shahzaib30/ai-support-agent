import asyncio

from flashrank import Ranker, RerankRequest
from loguru import logger

RERANKER_MODEL = "ms-marco-TinyBERT-L-2-v2"

_ranker: Ranker | None = None


def _get_ranker() -> Ranker:
    global _ranker
    if _ranker is None:
        _ranker = Ranker(model_name=RERANKER_MODEL)
    return _ranker


def _rerank_sync(query: str, chunks: list[dict], top_k: int) -> list[dict]:
    ranker = _get_ranker()
    passages = [
        {"id": i, "text": chunk["text"], "metadata": chunk["metadata"]}
        for i, chunk in enumerate(chunks)
    ]
    ranked = ranker.rerank(RerankRequest(query=query, passages=passages))

    results = []
    for passage in ranked[:top_k]:
        chunk = dict(chunks[passage["id"]])
        chunk["score"] = float(passage["score"])
        results.append(chunk)
    return results


async def rerank(query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    """Cross-encoder reranking of candidate chunks. Replaces each chunk's
    `score` with the reranker's relevance score (0..1)."""
    if not chunks:
        return []
    try:
        return await asyncio.to_thread(_rerank_sync, query, chunks, top_k)
    except Exception as e:
        logger.error(f"Reranking failed, falling back to retrieval order: {e}")
        return chunks[:top_k]
