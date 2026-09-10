import os
from loguru import logger
from dotenv import load_dotenv
from openai import OpenAI
from langsmith import traceable
from retriever import search

load_dotenv()

deepseek = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
)
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def retrieve(question: str) -> list[dict]:
    """
    Search FAISS for relevant chunks.
    Returns top 5 chunks.
    """
    try:
        chunks = search(question, top_k=5)
        logger.debug(f"Retrieved {len(chunks)} chunks")
        return chunks
    except Exception as e:
        logger.error(f"Error retrieving chunks: {e}")
        return []

def summarize_conversation(messages: list[dict]) -> str:
    if not messages:
        return ""
    history_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
    try:
        response = deepseek.chat.completions.create(
            model = MODEL,
            messages = [
                {
                    "role" : "system",
                    "content" : ("You are a conversation summarizer for a customer support System."
                                 "Summarize the following conversation in 2-3 sentences."
                                 "Include: the main issue the customer raised"
                                 "the customer's sentiment (frustrated/neutral/satisfied)"
                                 "and whether the issue was resolved or still open"
                                 "Be concise and factual"
                    ),
                },
                {
                    "role" : "user",
                    "content" : history_text
                },
            ],
            max_tokens = 150,
            temperature = 0.1,
        )

        summary = response.choices[0].message.content.strip()
        logger.debug(f"Generated summary: {summary[:80]}...")
        return summary

    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        return ""

def generate(
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

    response = deepseek.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=500,
        temperature=0.3,
    )

    answer = response.choices[0].message.content.strip()
    logger.debug(f"Generated answer: {answer[:80]}...")
    return answer


@traceable(name="rag_pipeline")
def run_rag_pipeline(
    question:     str,
    long_term_summary: str | None = None,
    chat_history: list[dict] | None = None,
) -> dict:
    """
    Simple RAG pipeline:
    1. Search FAISS for relevant chunks
    2. Send chunks to DeepSeek
    3. Return answer

    That's it. n8n handles everything else.
    """
    logger.info(f"RAG pipeline: {question[:60]}...")
    chunks = retrieve(question)
    answer = generate(question, chunks, chat_history, long_term_summary)

    return {
        "answer": answer,
        "chunks_used": len(chunks),
        "sources": [
            c["metadata"].get("source", "unknown")
            for c in chunks
        ],
    }