import os
import json
import faiss
import numpy as np
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv
from fastembed import TextEmbedding
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    Docx2txtLoader,
    DirectoryLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
DOCS_PATH        = "./docs"
FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./vector_store/faiss_index")
CHUNK_SIZE       = 512
CHUNK_OVERLAP    = 64

# load embedding model once
embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5")


# ─────────────────────────────────────────
# STEP 1 — LOAD DOCUMENTS
# ─────────────────────────────────────────
def load_documents(docs_path: str = DOCS_PATH) -> list:
    """
    Load all documents from docs folder.
    Supports PDF, TXT, DOCX.
    """
    logger.info(f"Loading documents from: {docs_path}")

    path = Path(docs_path)
    if not path.exists():
        logger.warning("Docs folder not found — creating it")
        path.mkdir(parents=True, exist_ok=True)
        return []

    documents = []
    loaders = {
        "**/*.pdf":  PyPDFLoader,
        "**/*.txt":  TextLoader,
        "**/*.docx": Docx2txtLoader,
    }

    for glob_pattern, loader_class in loaders.items():
        try:
            loader = DirectoryLoader(
                docs_path,
                glob=glob_pattern,
                loader_cls=loader_class,
                silent_errors=True,
            )
            docs = loader.load()
            documents.extend(docs)
            logger.info(f"Loaded {len(docs)} files matching {glob_pattern}")
        except Exception as e:
            logger.warning(f"Could not load {glob_pattern}: {e}")

    logger.info(f"Total documents loaded: {len(documents)}")
    return documents


# ─────────────────────────────────────────
# STEP 2 — CHUNK DOCUMENTS
# ─────────────────────────────────────────
def chunk_documents(documents: list) -> list:
    """
    Split documents into smaller chunks.
    """
    logger.info("Chunking documents...")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", "!", "?", ",", " "],
    )

    chunks = splitter.split_documents(documents)
    logger.info(f"Total chunks created: {len(chunks)}")
    return chunks


# ─────────────────────────────────────────
# STEP 3 — EMBED CHUNKS
# ─────────────────────────────────────────
def embed_chunks(chunks: list) -> tuple:
    """
    Convert chunks to vectors using fastembed.
    Returns: (embeddings, texts, metadatas)
    """
    logger.info(f"Embedding {len(chunks)} chunks...")

    texts = [chunk.page_content for chunk in chunks]
    metas = [
        {
            "source":   chunk.metadata.get("source", "unknown"),
            "page":     chunk.metadata.get("page", 0),
            "chunk_id": i,
        }
        for i, chunk in enumerate(chunks)
    ]

    # embed using fastembed — no API call, runs locally
    embeddings = np.array(
        list(embedding_model.embed(texts)),
        dtype=np.float32
    )

    logger.info(f"Embeddings shape: {embeddings.shape}")
    return embeddings, texts, metas


# ─────────────────────────────────────────
# STEP 4 — BUILD FAISS INDEX
# ─────────────────────────────────────────
def build_faiss_index(embeddings: np.ndarray) -> faiss.IndexFlatIP:
    """
    Build FAISS index from embeddings.
    Uses cosine similarity (Inner Product
    after L2 normalization).
    """
    logger.info("Building FAISS index...")

    faiss.normalize_L2(embeddings)

    dimension = embeddings.shape[1]
    index     = faiss.IndexFlatIP(dimension)
    index.add(embeddings)

    logger.info(f"FAISS index built — {index.ntotal} vectors")
    return index


# ─────────────────────────────────────────
# STEP 5 — SAVE TO DISK
# ─────────────────────────────────────────
def save_index(
    index:     faiss.IndexFlatIP,
    texts:     list,
    metadatas: list,
    path:      str = FAISS_INDEX_PATH,
) -> None:
    """
    Save FAISS index + texts + metadata to disk.
    """
    Path(path).mkdir(parents=True, exist_ok=True)

    faiss.write_index(index, f"{path}/index.faiss")

    with open(f"{path}/texts.json", "w", encoding="utf-8") as f:
        json.dump(texts, f, ensure_ascii=False, indent=2)

    with open(f"{path}/metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadatas, f, ensure_ascii=False, indent=2)

    logger.success(f"Saved to {path} — {index.ntotal} vectors")


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def ingest(docs_path: str = DOCS_PATH) -> dict:
    """
    Full ingestion pipeline:
    Load → Chunk → Embed → Index → Save
    """
    logger.info("Starting ingestion...")

    documents = load_documents(docs_path)
    if not documents:
        return {"status": "error", "message": "No documents found"}

    chunks = chunk_documents(documents)
    if not chunks:
        return {"status": "error", "message": "Chunking failed"}

    embeddings, texts, metadatas = embed_chunks(chunks)
    index = build_faiss_index(embeddings)
    save_index(index, texts, metadatas)

    return {
        "status":    "success",
        "documents": len(documents),
        "chunks":    len(chunks),
        "vectors":   index.ntotal,
    }


if __name__ == "__main__":
    result = ingest()
    print(result)