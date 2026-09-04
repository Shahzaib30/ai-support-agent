import os
import json
import faiss
import numpy as np
from loguru import logger
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./vector_store/faiss_index")
TOP_K            = 5

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
)


def embed_query(text: str) -> np.ndarray:
    """
    Convert query text to vector using DeepSeek.
    Returns numpy array of shape (1, dimensions).
    """
    response = client.embeddings.create(
        input=[text],
        model="text-embedding-3-small",
    )
    vector = np.array([response.data[0].embedding], dtype=np.float32)
    return vector



class VectorStore:
    def __init__(self, path: str = FAISS_INDEX_PATH):
        logger.info(f"Loading vector store from: {path}")

        self.index = faiss.read_index(f"{path}/index.faiss")

        with open(f"{path}/texts.json", "r", encoding="utf-8") as f:
            self.texts = json.load(f)

        with open(f"{path}/metadata.json", "r", encoding="utf-8") as f:
            self.metadatas = json.load(f)

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
    Convert question to vector using DeepSeek.
    Find top_k closest chunks in FAISS.
    Return chunks with text + metadata.
    """
    store = get_store()

    # embed query with DeepSeek
    embedding = embed_query(query)
    faiss.normalize_L2(embedding)

    # search FAISS
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