import os
import json

from importlib_metadata import metadata
import faiss
import numpy as np
from pathlib import Path
from loguru import logger
from dotenv impot load_doten
from openai impot OpenAI
from sentence_transformers import SentenceTransformer
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    Docx2txtLoader,
    DirectoryLoader,
)

from langchain.text_splitter import RecursiveCharacterTextSplitter

load_dotenv()


DOCS_PATH = "./docs"
FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./vector_store/faiss_index")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64


client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1")
)

# Step 1 : Load Documents

def load_documents(docs_path: str = DOCS_PATH):
    """
    load all documents from the docs folder. Support PDF, TXT, DOCS"""

    logger.info(f"Loading documents from {docs_path}...")
    path = Path(docs_path)
    documents = []

    if not path.exists():
        logger.error(f"Docs path {docs_path} does not exist.")
        path.mkdir(parents=True, exist_ok=True)
        return []
    loaders = {
        "**/*.pdf": PyPDFLoader,
        "**/*.txt": TextLoader,
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
            logger.info(f"Loaded {len(docs)} documents from {glob_pattern}.")
        except Exception as e:
            logger.error(f"Error loading documents from {glob_pattern}: {e}")
    logger.info("Finished loading documents. Total documents loaded: {len(documents)}")

# Chunk Documents

def chunk_documents(documents: list) -> list:
    """
    Split documents into smaller chunks for embedding."""

    logger.info("Chunking documents...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        seperators = ["\n\n", "\n", ".", "!", "?", ",", " ", ""],
    )

    chunks = splitter.split_documents(documents)
    logger.info(f"Chunked documents into {len(chunks)} chunks.")
    return chunks


# ADD Context to each chunk and embed them using the embedding model

def add_context_to_chunk(chunk_text: str, full_doc_text: str) -> str:
    """
    Use deepseek to prepend a short context
    summary to each chunk before embedding. 
    This is contextual retrieval.
    """

    try:
        prompt = f"""
        Here is a document:
        <document>
        {full_doc_text[:3000]}
        </document>
        
        Here is one chunk from that document:
        <chunk>
        {chunk_text}
        </chunk>
        
        Write a SHORT 1-2 sentence context that explains where this chunk sits 
        in the document and what it is about. This will be prepended to the chunk 
        to improve search retrieval. Reply with ONLY the context, nothing else.

        """
        response = client.responses.create(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            messages = [{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.0,
        )

        context = response.choices[0].message.content.strip()
        return f"{context}\n\n{chunk_text}"

    except Exception as e:
        logger.error(f"Error adding context to chunk: {e}")
        return chunk_text


# step 4 : Embed Chunks and Create FAISS Index

def embed_chunks(chunks: list, add_context: bool = True) -> tuple:
    """
    Embed all chunks using sentene-transformers.
    Optionally adds contextual retrieval context first.
    Return: (embeddings array, text list, metadatas list)"""

    logger.info("Embedding chunks...")
    model = SentenceTranformer(EMBEDDING_MODEL)

    texts = []
    metadatas = []

    for i, chunk in enumerate(chunks):
        text = chunk.page_content
        full_text = text

        if add_context:
            logger.debug(f"Adding context to chunk {i+1}/{len(chunks)}...")
            full_text = add_context_to_chunk(text, text)

        texts.append(full_text)
        metadatas.append({
            "source": chunk.metadata.get("source", "unknown"),
            "page": chunk.metadata.get("page", "unknown"),
            "chunk_id": i,
            "raw_text": text,
        })

        logger.info(f"Embedded chunk {i+1}/{len(chunks)}")
        embeddings = model.encode(texts, show_progress_bar=True, batch_size=32)
        logger.info(f"Finished embedding {len(chunks)} chunks.")

        return embeddings, texts, metadatas

# Step 5 : Create FAISS Index

def build_faiss_index(embeddings: np.ndarray) -> faiss.IndexFlatIP:
    """
    Build a Faiss index from the embeddings.
    Uses Inner Product (cosine similarity after normalization)"""
    logger.info("Building FAISS index...")
    faiss.normalize_L2(embeddings)
    dimension = embeddings.shape[1] 
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)

    logger.info(f"FAISS index built with {index.ntotal} vectors.")
    return index


def save_index(
        index: faiss.IndexFlatIP,
        texts: list,
        metadatas : list,
        path : str = FAISS_INDEX_PATH,
) -> None:
    """ Save Faiss index = texts + metadata to disk"""
    Path(path).mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, f"{path}/index.faiss")

    with open(f"{path}/texts.json", "w", encoding="utf-8") as f:
        json.dump(texts, f, ensure_ascii=False, indent=2)

    with open(f"{path}/metadatas.json", "w", encoding="utf-8") as f:
        json.dump(metadatas, f, ensure_ascii=False, indent=2)

    logger.success(f"FAISS index, texts, and metadata saved to {path}.")
    logger.info("Ingest process completed successfully.")



def ingest(docs_path: str = DOCS_PATH, add_context: bool = True) -> dict:

    """
    Full ingestion pipeline: load documents, chunk, embed, and save FAISS index."""
    logger.info("Starting ingestion process...")
    documents = load_documents(docs_path)
    if not documents:
        logger.warning("No documents found to ingest.")
        return {"status": "no_documents"}
    chunks = chunk_documents(documents)
    if not chunks:
        logger.warning("No chunks created from documents.")
        return {"status": "no_chunks"}
    
    embeddings, texts, metadatas = embed_chunks(chunks, add_context=add_context)

    index = build_faiss_index(embeddings)
    save_index(index, texts, metadatas)

    return {"status": "success", "num_documents": len(documents), "num_chunks": len(chunks), "vectors": index.ntotal, "index_path": FAISS_INDEX_PATH}


if __name__ == "__main__":
    result = ingest()
    print(result)
