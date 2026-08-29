import os
import json
import faiss
import numpy as np
from loguru import logger
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./vector_store/faiss_index")
EMBEDDING_MODEL  = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
TOP_K            = 5
class VectorStore:
    def __init__(self, path: str = FAISS_INDEX_PATH):
        logger.info(f"Loading vector store from: {path}")

        self.index = faiss.read_index(f"{path}/index.faiss")

        with open(f"{path}/texts.json", "r", encoding="utf-8") as f:
            self.texts = json.load(f)

        with open(f"{path}/metadata.json", "r", encoding="utf-8") as f:
            self.metadatas = json.load(f)

        self.model = SentenceTransformer(EMBEDDING_MODEL)

        logger.success(
            f"Vector store ready — "
            f"{self.index.ntotal} vectors, "
            f"{len(self.texts)} texts"
        )


_store: VectorStore | None = None

def get_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store


def search(query: str, top_k: int = TOP_K) -> list[dict]:
    """
    Convert question to vector.
    Find top_k closest chunks in FAISS.
    Return chunks with text + metadata.
    """
    store = get_store()
    
    embedding = store.model.encode([query])
    faiss.normalize_L2(embedding)
    
    scores, indices = store.index.search(embedding, top_k)
    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        results.append({
            "text":     store.texts[idx],
            "metadata": store.metadatas[idx],
            "score":    float(score),
        })

    logger.debug(f"Search returned {len(results)} chunks for: {query[:50]}")
    return results