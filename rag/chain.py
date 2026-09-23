import os

from dotenv import load_dotenv
from langsmith import traceable
from loguru import logger
from openai import AsyncOpenAI

from rag.condenser import condense_query
from rag.reranker import rerank
from rag.retriever import search

load_dotenv()

deepseek = AsyncOpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
)
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# Minimum reranked relevance score a top chunk must clear before we let the
# LLM answer from it. Below this, we assume the knowledge base doesn't cover
# the question and hand off to a human instead of risking a hallucination.
SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", 0.65))

FALLBACK_ANSWER = (
    "I don't have enough information to answer that confidently. "
    "I'm connecting you with a member of our support team who can help."
)


async def retrieve(question: str) -> list[dict]:
    """
    Hybrid search (dense + BM25, fused with RRF) over the vector store,
    followed by cross-encoder reranking. Returns the top reranked chunks.
    """
    try:
        candidates = await search(question, top_k=20)
        reranked = await rerank(question, candidates, top_k=5)
        logger.debug(f"Retrieved {len(reranked)} reranked chunks")
        return reranked
    except Exception as e:
        logger.error(f"Error retrieving chunks: {e}")
        return []


async def summarize_conversation(messages: list[dict]) -> str:
    if not messages:
        return ""
    history_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
    try:
        response = await deepseek.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": ("You are a conversation summarizer for a customer support System."
                                 "Summarize the following conversation in 2-3 sentences."
                                 "Include: the main issue the customer raised"
                                 "the customer's sentiment (frustrated/neutral/satisfied)"
                                 "and whether the issue was resolved or still open"
                                 "Be concise and factual"
                    ),
                },
                {
                    "role": "user",
                    "content": history_text
                },
            ],
            max_tokens=150,
            temperature=0.1,
        )

        summary = response.choices[0].message.content.strip()
        logger.debug(f"Generated summary: {summary[:80]}...")
        return summary

    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        return ""


async def generate(
    question:     str,
    chunks:       list[dict],
    chat_history: list[dict] | None = None,
    long_term_summary: str | None = None,
) -> str:
    """
    Send chunks + question to DeepSeek.
    Returns answer string.
    """
    context = "\n\n---\n\n".join([c["text"] for c in chunks])

    summary_section = ""
    if long_term_summary:
        summary_section = f"\nPrevious conversation summary:\n{long_term_summary}\n"

    system_prompt = (
        f"You are a helpful customer support AI assistant."
        f"{summary_section}\n"
        f"Answer questions based ONLY on the provided context.\n"
        f"If the context does not contain the answer, say:\n"
        f'"I don\'t have that information, please contact our support team."\n'
        f"Keep answers short, friendly, and clear."
    )

    messages = [{"role": "system", "content": system_prompt}]

    if chat_history:
        messages.extend(chat_history[-6:])

    messages.append({
        "role": "user",
        "content": f"Context:\n{context}\n\nQuestion: {question}"
    })

    response = await deepseek.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=500,
        temperature=0.3,
    )

    answer = response.choices[0].message.content.strip()
    logger.debug(f"Generated answer: {answer[:80]}...")
    return answer


@traceable(name="rag_pipeline")
async def run_rag_pipeline(
    question:     str,
    long_term_summary: str | None = None,
    chat_history: list[dict] | None = None,
) -> dict:
    """
    Hybrid RAG pipeline:
    1. Condense the question against chat history into a standalone search query
    2. Hybrid search (dense + BM25) + rerank
    3. If nothing clears the similarity threshold, fall back instead of
       hallucinating and signal that the conversation should be escalated
    4. Otherwise send chunks to DeepSeek and return the grounded answer
    """
    logger.info(f"RAG pipeline: {question[:60]}...")

    standalone_query = await condense_query(question, chat_history, deepseek, MODEL)
    chunks = await retrieve(standalone_query)

    top_score = chunks[0]["score"] if chunks else 0.0
    if not chunks or top_score < SIMILARITY_THRESHOLD:
        logger.warning(
            f"No chunks cleared similarity threshold "
            f"({top_score:.3f} < {SIMILARITY_THRESHOLD}) for: {question[:60]}"
        )
        return {
            "answer": FALLBACK_ANSWER,
            "chunks_used": 0,
            "sources": [],
            "low_confidence": True,
        }

    answer = await generate(question, chunks, chat_history, long_term_summary)

    return {
        "answer": answer,
        "chunks_used": len(chunks),
        "sources": [
            c["metadata"].get("source", "unknown")
            for c in chunks
        ],
        "low_confidence": False,
    }
