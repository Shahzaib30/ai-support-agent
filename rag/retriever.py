import os
import json
import re
from tkinter import TOP
import faiss
import numpy as np
from loguru import logger
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

load_dotenv()

FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./vector_store/faiss_index")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
TOP_K = 5
RRF_K = 60 # RECIPROCAL RANK FUSION


# LOAD INDEX

class VectorStore:
    """
    Load FAISS index, texts and metadata from disk.
    Keeps them in memory for fast retrieval."""

    def __init__(self, path: str = FAISS_INDEX_PATH):
        logger.info(f"Loading FAISS index from {path}...")
        self.index = faiss.read_index(os.path.join(path, "index.faiss"))

        with open(f"{path}/texts.json", "r", encoding="uft-8") as f:
            self.texts = json.load(f)
        with open(f"{path}/metadata.json", "r", encoding="utf-8") as f:
            self.metadata = json.load(f)

        self.model = SentenceTransformer(EMBEDDING_MODEL)
        tokenized = [text.lower().split() for text in self.texts]
        self.bm25 = BM25Okapi(tokenized)

        logger.success(
            f"Vector store loaded - {self.index.ntotal} vectors",
            f"{len(self.texts)} texts"
        )

_store : VectorStore | None = None

def get_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store

# Vector Search

def vector_search(query: str, top_k: int= TOP_K) -> list[dict]:
    """
    Semantic search using FAISS.
    Finds chunks that Mean the same thing as the query"""

    store = get_store()

    embedding = store.model.encode([query])
    faiss_normalize_L2(embedding)

    scores, indices = store.index.search(embedding, top_k)
    results = []

    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        results.append({
            "text": store.texts[idx],
            "metadata": store.metadata[idx],
            "score": float(score),
            "source" : "vecotr",
        })
        return results



#  BM25 Search

def keyword_search(query: str, top_k: int=TOP_K) -> list[dict]:
    """
    Keyword search using BM25.
    Finds chunks that contain the same keywords as the query"""

    store = get_store()
    tokenized_query = query.lower().split()
    scores = store.bm25.get_scores(tokenized_query)
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        if scores[idx] == 0:
            continue
        results.append({
            "text": store.texts[idx],
            "metadata": store.metadata[idx],
            "score": float(scores[idx]),
            "source": "keyword",
        })
    return results


# Reciprocal Rank Fusion (RRF) Search
# Merge both keyword + vector search results using RRF

def reciprocal_rank_fusion(result_list: list[list[dict]], k: int = RRF_K) -> list[dict]:
    """
    Merge multiple search results using Reciprocal Rank Fusion (RRF).
    Each result in result_list is a list of dictionaries with 'text', 'metadata', and 'score'."""

    scores: dict[int, float] = {}
    chunk_map : dict[int, dict] = {}

    for result in result_list:
        for rank, item in enumerate(result):
            chunk_id = item["metadata"]["chunk_id"]
            if chunk_id not in scores:
                scores[chunk_id] = 0.0
                chunk_map[chunk_id] = item

            scores[chunk_id] += 1 / (k + rank)

    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)

    fused = []
    for chunk_id in sorted_ids:
        item = chunk_map[chunk_id].copy()
        item["rrf_score"] = scores[chunk_id]
        fused.append(item)

    return fused


# def hybrid search
# combine both vector and keyword search results using RRF

def hybrid_search(query: str, top_k:int=TOP_K) -> list[dict]:
    """
    Hybrid search = bm25 + vector search + rrf fusion
    Best of both worlds - semantic + keyword search
    """
    logger.debug(f"Performing hybrid search for query: {query}")

    vector_results = vector_search(query, top_k)
    keyword_results = keyword_search(query, top_k)

    fused_results = reciprocal_rank_fusion([vector_results, keyword_results], k=RRF_K)
    top_results = fused_results[:top_k]
    logger.debug(f"Hybrid search results: vector: {len(vector_results)}, keyword: {len(keyword_results)}, fused: {len(top_results)}")

    return top_results


# multi-query + hybrid search
# generate multiple queries from the original query and perform hybrid search on each, then fuse results using RRF

def multi_query_hybrid_search(queries: str, top_k:int=TOP_K) -> list[dict]:
    """
    Multi-query hybrid search = generate multiple queries from the original query
    and perform hybrid search on each, then fuse results using RRF.
    This is useful for long queries that can be broken down into multiple sub-queries.
    """

    logger.debug(f"Performing multi-query hybrid search for query: {query}")

    all_results = []
    for query in queries:
        results = hybrid_search(query, top_k)
        all_results.append(results)

    fused = reciprocal_rank_fusion(all_results, k=RRF_K)
    return fused[:top_k]


# Hyde Search 
# generate a hypothetical answer to the query and perform hybrid search on that, then fuse results using RRF

def hyde_search(hypothetical_answer: str, top_k:int=TOP_K) -> list[dict]:
    """
    Hyde search = generate a hypothetical answer to the query and perform hybrid search on that,
    then fuse results using RRF. This is useful for queries that are difficult to answer directly.
    """

    logger.debug(f"Performing hyde search for hypothetical answer: {hypothetical_answer}")

    results = hybrid_search(hypothetical_answer, top_k)
    return results
