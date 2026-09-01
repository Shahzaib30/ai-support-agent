from logging import Logger
import os
import time
import json

from requests import get
import httpx
import asyncpg
from rag.ingest import ingest
import redis.asyncio as aioredis
from loguru import logger
from dotenv import load_dotenv
from datetime import datetime
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter, Histogram, Gauge
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

import sys
sys.path.append("./rag")
sys.path.append("./sentiment")
from chain import run_rag_pipeline
from analyzer import run_sentiment_pipeline

load_dotenv()

# Seting up Prometheus metrics

MESSAGE_TOTAL = Counter(
    "message_total",
    "Total message processed"
)

ESCALATION_TOTAL = Counter(
    "escalation_total",
    "Total escalations detected"
)

CACHE_HITS = Counter(
    "cache_hits_total",
    "Total Redis cache hits"
)

CACHE_MISSES = Counter(
    "cache_misses_total",
    "Total Redis cache misses"
)

RESPONSE_TIME = Histogram(
    "rag_response_time_seconds",
    "RAG Pipeline response time in seconds"
)

ACTIVE_CONVERSATIONS = Gauge(
    "active_conversations",
    "Number of active conversations"
)


# Globals

db_pool = None
redis_client = None

deepseek = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"),
                  base_url=os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com"))

# STARTUP AND SHUTDOWN EVENTS

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool, redis_client
    logger.info("Starting up...")

    # connect postgres
    db_pool = await asyncpg.create_pool(
        dsn=os.getenv("DATABASE_URL"),
        min_size=2,
        max_size=10
    )

    logger.success("Database connection pool created")

    # redis connection
    redis_client = aioredis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379"),
        encoding="utf-8",
        decode_responses=True
    )

    logger.success("Redis connection established")
    logger.success("Startup complete")

    yield

    await db_pool.close()
    await redis_client.close()
    logger.info("Shutdown complete")


# APP

app = FastAPI(
    title="RAG + Sentiment Analysis API",
    description="An API that combines Retrieval-Augmented Generation (RAG) and Sentiment Analysis.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# attach prometheus 
Instrumentator().instrument(app).expose(app, include_in_schema=False)

# pydantic models

class ChatRequest(BaseModel):
    telegram_chat_id : str
    message : str
    customer_name : str | None = None

class ChatResponse(BaseModel):
    answer : str
    escalated : bool
    cache_hit : bool
    sentiment_label : str
    sentiment_score : float


# Helpers 


async def get_cache(key : str) -> str | None:
    """ Get value for cached answer. """

    try:
        cached = await redis_client.get(key)
        if cached:
            CACHE_HITS.inc()
            return cached
        CACHE_MISSES.inc()
        return None

    except Exception as e:
        logger.error(f"Error fetching from cache: {e}")
        return None


async def set_cache(key : str, value: str, expire : int = 3600) -> None:
    """Store answer in redis for 1 hour"""
    try:
        await redis_client.setex(f"cache: {key}", expire, value)
        logger.debug(f"Stored answer in cache for key: {key}")
    except Exception as e:
        logger.error(f"Error storing in cache: {e}")



# Postgres Helper

async def get_or_create_conversation(chat_id: str, customer_name : str | None) -> str:
    """ Get existing conversation or create a new one in the database. """

    async with db_pool.acquire() as conn:
        # Check if conversation exists
        row = await conn.fetchrow(
            "SELECT id FROM conversations WHERE telegram_chat_id = $1",
            chat_id
        )
        if row:
            return row["id"]

        # Create new conversation
        new_id = await conn.fetchval(
            "INSERT INTO conversations (telegram_chat_id, customer_name, created_at) VALUES ($1, $2, $3) RETURNING id",
            chat_id,
            customer_name
        )
        ACTIVE_CONVERSATIONS.inc()
        logger.info(f"Created new conversation with id: {new_id} for chat_id: {chat_id}")
        return str(new_id)

async def save_message(
            conversation_id : str,
            role : str,
            content : str,
            sentiment_score : float | None = None,
            sentiment_label : str | None = None,
            rag_used : bool = False,
            cache_hit : bool = False,
            response_ms: int | None = None
    ):
        """ Save message to the database. """
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO messages (conversation_id, role, content, sentiment_score, sentiment_label, rag_used, cache_hit, response_ms) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                conversation_id,
                role,
                content,
                sentiment_score,
                sentiment_label,
                rag_used,
                cache_hit,
                response_ms            
                )
            

async def get_chat_history(conversation_id : str) -> list[dict]:
    """Get last 6 messages for this convesation.
    Used as memory contenxt for deepseek"""

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT role, content FROM messages WHERE conversation_id = $1 ORDER BY created_at DESC LIMIT 6",
            conversation_id
        )
        return [{"role": r["role"], "content": r["content"]} for r in rows]


async def get_sentiment_history(conversation_id : str) -> list[dict]:
    """Get last 10 messages. for escalation check"""

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT sentiment_score, sentiment_label FROM messages WHERE conversation_id = $1 ORDER BY created_at DESC LIMIT 10",
            conversation_id
        )
        return [{"sentiment_score": r["sentiment_score"], "sentiment_label": r["sentiment_label"]} for r in rows]

async def mark_escalation(conversation_id : str, reason: str) -> None:
    """Mark conversation as escalated in the database."""
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE conversations SET escalated = TRUE WHERE id = $1",
            conversation_id
        )

        await conn.execute(
            "INSERT INTO escalations (conversation_id, created_at) VALUES ($1, $2)",
            conversation_id,
            reason,
        )


# slack alert 
async def send_slack_alert(
        chat_id : str,
        customer_name : str | None,
        last_message : str,
        reason : str,
) -> None:
    """ Send escalation alert to slack"""

    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not set. Skipping slack alert.")
        return
    name = customer_name or chat_id

    payload = {
        "text" : (
            f"🚨 Escalation Alert 🚨\n"
            f"Customer: {name}\n"
            f"Chat ID: {chat_id}\n"
            f"Last Message: {last_message}\n"
            f"Reason: {reason}\n"
        )
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
            logger.info(f"Sent slack alert for chat_id: {chat_id}")
        except Exception as e:
            logger.error(f"Error sending slack alert: {e}")

# n8n calls this on every telegram message

@app.post("/chat", response_model=ChatResponse) 
async def chat(request: ChatRequest):
    """
    Main flow : 
    1. get conversations in postgres
    2. check redis cache
    3. if cache miss, run RAG pipeline
    4. run sentiment analysis
    5. check escalation
    6. log evverything to postgres
    7. return answer to n8n"""

    start_time = time.time()

    logger.info(f"Received message from chat_id: {request.telegram_chat_id}")
    MESSAGE_TOTAL.inc()

    conversation_id = await get_or_create_conversation(request.telegram_chat_id, request.customer_name)

    cache_hit = False
    answer = await get_cache(request.message)

    if answer:
        cache_hit = True
        logger.info(f"Cache hit for message: {request.message}")
    else:
        chat_history = await get_chat_history(conversation_id)

        with RESPONSE_TIME.time():
            answer = await run_rag_pipeline(
                query=request.message,
                chat_history=chat_history
            )

        answer = answer["answer"]
        await set_cache(request.message, answer)




    sentiment_history = await get_sentiment_history(answer)
    sentiment_result = run_sentiment_pipeline(
        message=request.message,
        sentiment_history=sentiment_history
    )

    current_sentiment = sentiment_result["current_sentiment"]
    escalation = sentiment_result["escalation"]

    escalation = False

    if escalation["should_escalate"]:
        escalation = True
        ESCALATION_TOTAL.inc()
        reason = escalation["reason"]
        await mark_escalation(conversation_id, reason)
        await send_slack_alert(
            chat_id=request.telegram_chat_id,
            customer_name=request.customer_name,
            last_message=request.message,
            reason=reason
        )

    response_time_ms = int((time.time() - start_time) * 1000)

    await save_message(
        conversation_id=conversation_id,
        role="user",
        content=request.message,
        sentiment_score=current_sentiment["score"],
        sentiment_label=current_sentiment["label"],
        rag_used=not cache_hit,
        cache_hit=cache_hit,
        response_ms=response_time_ms
    )   

    await save_message(
        conversation_id = conversation_id,
        role = "assistant",
        content = answer,
    )

    logger.success(f"Processed message for chat_id: {request.telegram_chat_id} in {response_time_ms} ms. Escalation: {escalation}")


    return ChatResponse(
        answer=answer,
        escalated=escalation,
        cache_hit=cache_hit,
        sentiment_label=current_sentiment["label"],
        sentiment_score=current_sentiment["score"]
    )


@app.post("/ingest")
async def ingest_document():
    """
    Ingest a document into the RAG system.
    This endpoint is used to add new documents to the knowledge base.
    """

    try: 
        sys.path.append("./rag")
        results = ingest()
        return results
    except Exception as e:
        logger.error(f"Error ingesting document: {e}")
        raise HTTPException(status_code=500, detail="Error ingesting document")

    
@app.get("/stats")
async def get_stats():
    """
    Get basic stats about the system.
    """
    async with db_pool.acquire() as conn:
        stats = await conn.fetchrow(
                """SELECT
               COUNT(*) FILTER (WHERE role = 'user') as total_messages,
               COUNT(DISTINCT conversation_id)        as total_conversations,
               AVG(sentiment_score)
                 FILTER (WHERE role = 'user')         as avg_sentiment,
               AVG(response_time_ms)
                 FILTER (WHERE role = 'user')         as avg_response_ms,
               COUNT(*) FILTER (WHERE cache_hit = true
                 AND role = 'user')                   as cache_hits
               FROM messages
               WHERE created_at >= CURRENT_DATE"""
        )

        escalation  = await conn.fetchrow(
            """SELECT COUNT(*) as total_escalations
               FROM escalations
               WHERE created_at >= CURRENT_DATE"""
        )        

        total_msgs = stats["total_messages"] or 0
        cache_hits = stats["cache_hits"] or 0

        return {
            "today" : {
                "total_messages" : total_msgs,
                "total_conversations" : stats["total_conversations"] or 0,
                "avg_sentiment" : float(stats["avg_sentiment"] or 0),
                "avg_response_ms" : float(stats["avg_response_ms"] or 0),
                "cache_hit_rate" : (cache_hits / total_msgs * 100) if total_msgs > 0 else 0,
                "total_escalations" : escalation["total_escalations"] or 0
            }
        }
@app.get("/health")
async def get_health():
    """
    Get the health status of the system.
    """
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main.app", host= os.getenv("API_HOST", "0.0.0.0"), port=os.getenv("API_PORT", 8000), reload=True)