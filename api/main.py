import os
import sys
import time
import httpx
import asyncpg
import redis.asyncio as aioredis
from loguru import logger
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter, Histogram, Gauge
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

sys.path.append("./rag")
sys.path.append("./sentiment")
from chain import run_rag_pipeline
from analyzer import analyze, check_escalation

load_dotenv()

# ─────────────────────────────────────────
# PROMETHEUS METRICS
# ─────────────────────────────────────────
MESSAGES_TOTAL = Counter("messages_total", "Total messages processed")
ESCALATIONS_TOTAL = Counter("escalations_total", "Total escalations triggered")
CACHE_HITS = Counter("cache_hits_total", "Total Redis cache hits")
CACHE_MISSES = Counter("cache_misses_total", "Total Redis cache misses")
RESPONSE_TIME = Histogram("rag_response_seconds", "RAG pipeline response time in seconds")
ACTIVE_CONVERSATIONS = Gauge("active_conversations", "Currently active conversations")

# ─────────────────────────────────────────
# GLOBALS
# ─────────────────────────────────────────
db_pool      = None
redis_client = None

deepseek = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
)


# ─────────────────────────────────────────
# STARTUP + SHUTDOWN
# ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool, redis_client
    logger.info("Starting up...")

    db_pool = await asyncpg.create_pool(
        dsn=os.getenv("DATABASE_URL"),
        min_size=2,
        max_size=10,
    )
    logger.success("Database connection pool created")

    count = await db_pool.fetchval("SELECT COUNT(*) FROM conversations")
    ACTIVE_CONVERSATIONS.set(count or 0)
    logger.info(f"Restored {count} conversations to gauge")
    
    redis_client = aioredis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379"),
        encoding="utf-8",
        decode_responses=True,
    )
    logger.success("Redis connection established")
    logger.success("Startup complete")

    yield

    await db_pool.close()
    await redis_client.close()
    logger.info("Shutdown complete")


# ─────────────────────────────────────────
# APP
# ─────────────────────────────────────────
app = FastAPI(title="AI Support Agent", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app, include_in_schema=False)


# ─────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────
class ChatRequest(BaseModel):
    telegram_chat_id: str
    message:          str
    customer_name:    str | None = None

class ChatResponse(BaseModel):
    answer:          str
    escalated:       bool
    cache_hit:       bool
    sentiment_label: str
    sentiment_score: float


# ─────────────────────────────────────────
# REDIS HELPERS
# ─────────────────────────────────────────
async def get_cache(key: str) -> str | None:
    try:
        cached = await redis_client.get(f"cache:{key}")
        if cached:
            CACHE_HITS.inc()
            logger.debug(f"Cache HIT: {key[:50]}")
            return cached
        CACHE_MISSES.inc()
        return None
    except Exception as e:
        logger.warning(f"Cache get failed: {e}")
        return None

async def set_cache(key: str, value: str, ttl: int = 3600) -> None:
    try:
        await redis_client.setex(f"cache:{key}", ttl, value)
        logger.debug(f"Cached: {key[:50]}")
    except Exception as e:
        logger.warning(f"Cache set failed: {e}")


# ─────────────────────────────────────────
# POSTGRES HELPERS
# ─────────────────────────────────────────
async def get_or_create_conversation(
    chat_id:       str,
    customer_name: str | None,
) -> str:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM conversations WHERE telegram_chat_id = $1",
            chat_id,
        )
        if row:
            return str(row["id"])

        new_id = await conn.fetchval(
            """INSERT INTO conversations (telegram_chat_id, customer_name)
               VALUES ($1, $2) RETURNING id""",
            chat_id,
            customer_name,
        )
        ACTIVE_CONVERSATIONS.inc()
        logger.info(f"New conversation: {chat_id}")
        return str(new_id)


async def save_message(
    conversation_id: str,
    role:            str,
    content:         str,
    sentiment_score: float | None = None,
    sentiment_label: str | None   = None,
    rag_used:        bool          = False,
    cache_hit:       bool          = False,
    response_ms:     int | None   = None,
) -> None:
    async with db_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO messages
               (conversation_id, role, content, sentiment_score,
                sentiment_label, rag_used, cache_hit, response_time_ms)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
            conversation_id, role, content,
            sentiment_score, sentiment_label,
            rag_used, cache_hit, response_ms,
        )


async def get_chat_history(conversation_id: str) -> list[dict]:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT role, content FROM messages
               WHERE conversation_id = $1
               ORDER BY created_at DESC LIMIT 6""",
            conversation_id,
        )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def get_sentiment_history(conversation_id: str) -> list[dict]:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT sentiment_label, sentiment_score
               FROM messages
               WHERE conversation_id = $1
               AND role = 'user'
               AND sentiment_label IS NOT NULL
               ORDER BY created_at DESC LIMIT 10""",
            conversation_id,
        )
    result = [
        {"label": r["sentiment_label"], "score": r["sentiment_score"]}
        for r in rows
    ]
    return list(reversed(result))


async def mark_escalated(conversation_id: str, reason: str) -> None:
    async with db_pool.acquire() as conn:
        await conn.execute(
            """UPDATE conversations
               SET is_escalated = true, escalated_at = NOW(), status = 'escalated'
               WHERE id = $1""",
            conversation_id,
        )
        await conn.execute(
            """INSERT INTO escalations (conversation_id, reason, slack_notified)
               VALUES ($1, $2, true)""",
            conversation_id,
            reason,
        )


# ─────────────────────────────────────────
# SLACK
# ─────────────────────────────────────────
async def send_slack_alert(
    chat_id:       str,
    customer_name: str | None,
    last_message:  str,
    reason:        str,
) -> None:
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("No Slack webhook configured")
        return

    name    = customer_name or chat_id
    payload = {
        "text": (
            f"🚨 *Escalation Alert*\n"
            f"*Customer:* {name}\n"
            f"*Reason:* {reason}\n"
            f"*Last message:* {last_message[:200]}"
        )
    }

    async with httpx.AsyncClient() as client:
        try:
            await client.post(webhook_url, json=payload, timeout=5)
            logger.info(f"Slack alert sent for: {chat_id}")
        except Exception as e:
            logger.error(f"Slack alert failed: {e}")


# ─────────────────────────────────────────
# MAIN ENDPOINT
# ─────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    start_time = time.time()
    logger.info(f"Received message from chat_id: {request.telegram_chat_id}")
    MESSAGES_TOTAL.inc()

    # step 1: get/create conversation
    conversation_id = await get_or_create_conversation(
        request.telegram_chat_id,
        request.customer_name,
    )

    # step 2: check cache
    cache_hit = False
    answer    = await get_cache(request.message)

    if answer:
        cache_hit = True
        logger.info("Served from cache")
    else:
        # step 3: run RAG
        chat_history = await get_chat_history(conversation_id)
        with RESPONSE_TIME.time():
            rag_result = run_rag_pipeline(
                question=request.message,
                chat_history=chat_history,
            )
        answer = rag_result["answer"]
        await set_cache(request.message, answer)

    # step 4: analyze sentiment of current message
    current_sentiment = analyze(request.message)
    response_ms = int((time.time() - start_time) * 1000)

    # step 5: save user message FIRST (so it's in history for escalation check)
    await save_message(
        conversation_id=conversation_id,
        role="user",
        content=request.message,
        sentiment_score=current_sentiment["score"],
        sentiment_label=current_sentiment["label"],
        rag_used=not cache_hit,
        cache_hit=cache_hit,
        response_ms=response_ms,
    )

    # step 6: fetch full sentiment history (now includes current message)
    sentiment_history = await get_sentiment_history(conversation_id)
    logger.debug(f"Sentiment history ({len(sentiment_history)} messages): {sentiment_history}")

    # step 7: check escalation against full history
    escalation = check_escalation(sentiment_history)

    escalated = False
    if escalation["should_escalate"]:
        escalated = True
        ESCALATIONS_TOTAL.inc()
        await mark_escalated(conversation_id, escalation["reason"])
        await send_slack_alert(
            chat_id=request.telegram_chat_id,
            customer_name=request.customer_name,
            last_message=request.message,
            reason=escalation["reason"],
        )

    # step 8: save bot message
    await save_message(
        conversation_id=conversation_id,
        role="assistant",
        content=answer,
    )

    logger.success(
        f"Done in {response_ms}ms — "
        f"sentiment: {current_sentiment['label']} ({current_sentiment['score']}) — "
        f"consecutive negatives: {escalation['consecutive_negatives']} — "
        f"escalated: {escalated}"
    )

    return ChatResponse(
        answer=answer,
        escalated=escalated,
        cache_hit=cache_hit,
        sentiment_label=current_sentiment["label"],
        sentiment_score=current_sentiment["score"],
    )


# ─────────────────────────────────────────
# INGEST
# ─────────────────────────────────────────
@app.post("/ingest")
async def ingest_documents():
    try:
        from ingest import ingest
        result = ingest()
        return result
    except Exception as e:
        logger.error(f"Error ingesting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────
# STATS
# ─────────────────────────────────────────
@app.get("/stats")
async def get_stats():
    async with db_pool.acquire() as conn:
        stats = await conn.fetchrow(
            """SELECT
               COUNT(*) FILTER (WHERE role = 'user')  as total_messages,
               COUNT(DISTINCT conversation_id)         as total_conversations,
               AVG(sentiment_score)
                 FILTER (WHERE role = 'user')          as avg_sentiment,
               AVG(response_time_ms)
                 FILTER (WHERE role = 'user')          as avg_response_ms,
               COUNT(*) FILTER (WHERE cache_hit = true
                 AND role = 'user')                    as cache_hits
               FROM messages
               WHERE created_at >= CURRENT_DATE"""
        )
        escalations = await conn.fetchval(
            "SELECT COUNT(*) FROM escalations WHERE created_at >= CURRENT_DATE"
        )

    total_msgs = stats["total_messages"] or 0
    cache_hits = stats["cache_hits"] or 0

    return {
        "today": {
            "total_messages":      total_msgs,
            "total_conversations": stats["total_conversations"] or 0,
            "total_escalations":   escalations or 0,
            "avg_sentiment":       round(float(stats["avg_sentiment"] or 0), 2),
            "avg_response_ms":     round(float(stats["avg_response_ms"] or 0)),
            "cache_hit_rate":      round((cache_hits / total_msgs * 100) if total_msgs > 0 else 0, 1),
        }
    }


# ─────────────────────────────────────────
# HEALTH
# ─────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}


# ─────────────────────────────────────────
# RUN
# ─────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", 8000)),
        reload=True,
    )