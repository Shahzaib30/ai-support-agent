import asyncio
import json
import os
import pickle

import faiss
import numpy as np
from dotenv import load_dotenv
from fastembed import TextEmbedding
from loguru import logger
from rank_bm25 import BM25Okapi

from rag.hybrid import reciprocal_rank_fusion
from rag.text_utils import tokenize

load_dotenv()


FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./vector_store/faiss_index")
DENSE_CANDIDATES = 20
SPARSE_CANDIDATES = 20
FUSED_CANDIDATES = 20

embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5")


def embed_query(text: str) -> np.ndarray:
    vectors = list(embedding_model.embed([text]))
    return np.array(vectors, dtype=np.float32)


class VectorStore:
    def __init__(self, path: str = FAISS_INDEX_PATH):
        logger.info(f"Loading vector store from: {path}")

        self.index = faiss.read_index(f"{path}/index.faiss")

        with open(f"{path}/texts.json", "r", encoding="utf-8") as f:
            self.texts = json.load(f)

        with open(f"{path}/metadata.json", "r", encoding="utf-8") as f:
            self.metadatas = json.load(f)

        bm25_path = f"{path}/bm25.pkl"
        if os.path.exists(bm25_path):
            with open(bm25_path, "rb") as f:
                self.bm25: BM25Okapi | None = pickle.load(f)
        else:
            logger.warning("No BM25 index found — sparse retrieval disabled until re-ingest")
            self.bm25 = None

        logger.success(
            f"Vector store ready — "
            f"{self.index.ntotal} vectors, "
            f"{len(self.texts)} texts, "
            f"bm25={'yes' if self.bm25 else 'no'}"
        )


_store: VectorStore | None = None


def get_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store


def _dense_search_sync(query: str, top_k: int) -> list[int]:
    store = get_store()
    embedding = embed_query(query)
    faiss.normalize_L2(embedding)
    _, indices = store.index.search(embedding, top_k)
    return [int(idx) for idx in indices[0] if idx != -1]


def _sparse_search_sync(query: str, top_k: int) -> list[int]:
    store = get_store()
    if store.bm25 is None:
        return []
    scores = store.bm25.get_scores(tokenize(query))
    ranked = np.argsort(scores)[::-1][:top_k]
    return [int(idx) for idx in ranked if scores[idx] > 0]


async def search(query: str, top_k: int = FUSED_CANDIDATES) -> list[dict]:
    """
    Hybrid retrieval: dense (FAISS cosine) + sparse (BM25 keyword) search,
    fused with Reciprocal Rank Fusion. Runs the blocking FAISS/BM25 calls in
    a worker thread so the event loop isn't blocked during webhook handling.
    """
    store = get_store()

    dense_ids, sparse_ids = await asyncio.gather(
        asyncio.to_thread(_dense_search_sync, query, DENSE_CANDIDATES),
        asyncio.to_thread(_sparse_search_sync, query, SPARSE_CANDIDATES),
    )

    fused = reciprocal_rank_fusion(dense_ids, sparse_ids)[:top_k]

    results = []
    for doc_id, fused_score in fused:
        results.append({
            "text": store.texts[doc_id],
            "metadata": store.metadatas[doc_id],
            "score": float(fused_score),
        })

    logger.debug(
        f"Hybrid search returned {len(results)} candidates "
        f"(dense={len(dense_ids)}, sparse={len(sparse_ids)}) for: {query[:50]}"
    )
    return results
