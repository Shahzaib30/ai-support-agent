from logging import Logger
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
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

sys.path.append("./rag")
sys.path.append("./sentiment")
from chain import run_rag_pipeline, summarize_conversation
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
    conversation_id: str = ""

class HumanReplyRequest(BaseModel):
    conversation_id: str
    message: str
    agent_name : str | None = None

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
    return [
        {
            "role":    "assistant" if r["role"] == "human_agent" else r["role"],
            "content": r["content"],
        }
        for r in reversed(rows)
    ]

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

async def get_conversation_summary(conversation_id : str) -> str:
    async with db_pool.acquire() as conn:
        summary = await conn.fetchval(
            "SELECT summary FROM conversations where id = $1",
            conversation_id,
        )
        return summary or ""

async def update_conversation_summary(conversation_id : str, summary : str) -> None:
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE conversations SET summary = $1 WHERE id = $2",
            summary,
            conversation_id,
        )
        logger.info(f"Updated conversation {conversation_id} summary: {summary[:80]}...")

async def get_messages_for_summary(conversation_id : str) -> list[dict]:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT role, content FROM messages
               WHERE conversation_id = $1
               ORDER BY created_at DESC LIMIT 20""",
            conversation_id,
        )
    return [
        {
            "role":    "assistant" if r["role"] == "human_agent" else r["role"],
            "content": r["content"],
        }
        for r in reversed(rows)
    ]

async def get_total_message_count(conversation_id : str) -> int:
    async with db_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = $1",
            conversation_id,
        )    
    return count or 0

async def get_conversation_status(conversation_id : str) -> str:
    async with db_pool.acquire() as conn:
        status = await conn.fetchval(
            "SELECT status FROM conversations WHERE id = $1",
            conversation_id,
        )
    return status or "active"


async def check_escalation_timeout(conversation_id: str, timeout_minutes: int = 5) -> tuple[bool,bool]:
    """Returns (timeout, human replied) timeout -> true if escalation older then timeout minutes
    human replied -> true if any human agent message exists"""

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT escalated_at,
            EXISTS(
                SELECT 1 FROM messages
                WHERE conversation_id = $1
                AND role = 'human_agent')
                as human_replied 
                FROM conversations
                where id = $1""",
                conversation_id,
        )

        if not row or not row["escalated_at"]:
            return False, False

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        escalated_at = row["escalated_at"].replace(tzinfo=timezone.utc)
        elapsed = (now - escalated_at).total_seconds()/60

        timed_out = elapsed > timeout_minutes
        human_replied = row["human_replied"]

        logger.info(
            f"Escalation check: {elapsed:.1f} min elapsed |"
            f"Human_replied = {human_replied} | time_out = {timed_out}"
        )
        return timed_out, human_replied

async def auto_resolve_conversation(conversation_id: str) -> None:
    """ Auto resolve escalation after timeout. Sets status back to active so bot resume"""

    async with db_pool.acquire() as conn:
        await conn.execute(
            """UPDATE conversations
                SET status = 'active', is_escalated = false
                WHERE id = $1""", 
                conversation_id,
        )

        await conn.execute(
            """UPDATE escalations
            SET resolved = true, resolved_at = NOW()
            WHERE conversation_id = $1 AND resolved = false""",
            conversation_id,
        )

        logger.info(f"Auto Resolved after timeout: {conversation_id}")


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
# whatsapp integration

async def send_whatsapp_message(to: str, message: str) -> None:
    "Send a text message back to customer via whatsapp cloud api"
    token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    if not token or not phone_number_id:
        logger.warning("WhatsApp API not configured")
        return
    url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to" : to,
        "type" : "text",
        "text" : {"body" : message},
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url, 
                payload=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            logger.info(f"WhatsApp message sent to {to}: {message[:50]}...")
        except Exception as e:
            logger.error(f"WhatsApp message failed: {e}")


# ─────────────────────────────────────────
# MAIN ENDPOINT
# ─────────────────────────────────────────

@app.get("/whatsapp")
async def whatsapp_verify(request: Request):
    """Meta calls this once to verify your webhhook.
    Must Return the challenge string or Meta won't connect."""

    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN")

    if mode == "subscribe" and token == verify_token:
        logger.info("WhatsApp webhook verified")
        return int(challenge)

    raise HTTPException(status_code=403, detail="Verification failed")

@app.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Meta sends all incomming whatsapp messages here. Runs them through exisint chat() logic and replies"""

    body = await request.json()
    try:
        entry = body["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            return {"status" : "ignored"}

        msg = value["messages"][0]
        from_number = msg["from"]
        message_text = msg["text"]["body"]
        customer_name = value.get("contacts", [{}])[0].get("profile", {}).get("name", None)

        logger.info(f"Received Whatsapp from {from_number}: {message_text[:50]}...")

        conversation_id = await get_or_create_conversation(from_number, customer_name)

        # HITL Gate
        conv_status = await get_conversation_status(conversation_id)
        if conv_status == "escalated":
            timed_out, human_replied = await check_escalation_timeout(conversation_id, timeout_minutes=5)
            if human_replied:
                await send_whatsapp_message(from_number, "A human Agentis handling your case. Please wait..")
                return {"status" : "ok"}
            elif not timed_out:
                await send_whatsapp_message(from_number, "Our support team has been notified. A human agent will be with you shortly. Please wait.")
                return {"status" : "ok"}
            else:
                await auto_resolve_conversation(conversation_id)

        # explicit escalation check
        HUMAN_REQUEST_PHRASES = [
            "talk to agent",     "talk to human",    "talk to a human",
            "real person",       "human agent",      "connect me to",
            "transfer me",       "speak to someone", "i want a human",
            "need a human",      "get me a human",   "want to speak",
            "want to talk to",   "actual person",    "live agent",
            "speak to a person", "speak to agent",   "to an agent",
            "to a human",        "to a human agent", "to a real person",
            "to a live agent",   "to a support agent","to a support person",
            "to a support representative", "to a customer service agent",
            "to a customer service representative", "to a customer support agent",
            "to a customer support representative", "to a customer care agent",
            "to a customer care representative", "to a technical support agent",
            "to a technical support representative", "to a help desk agent",
            "to a help desk representative", "to a service desk agent",
            "to a service desk representative", "to a support specialist",
            "to a customer service specialist", "to a customer support specialist",
            "to a customer care specialist", "to a technical support specialist",
            "to a help desk specialist", "to a service desk specialist", "to a support representative", "to a customer service representative",
            "to a customer support representative", "to a customer care representative", "to a technical support representative", "to a help desk representative",
            "to a service desk representative", "to a support agent", "to a customer service agent", "to a customer support agent", "to a customer care agent", "to a technical support agent",
            "to a help desk agent", "to a service desk agent", "to a support specialist", "to a customer service specialist", "to a customer support specialist", "to a customer care specialist", "to a technical support specialist", "to a help desk specialist", "to a service desk specialist", "to a support representative", "to a customer service representative", "to a customer support representative", "to a customer care representative", "to a technical support representative", "to a help desk representative", "to a service desk representative"
            ]
        if any(phrase in message_text.lower() for phrase in HUMAN_REQUEST_PHRASES):
            await mark_escalated(conversation_id, "Customer explicitly requested a human agent")

            await send_slack_alert(
                chat_id= from_number,
                customer_name = customer_name,
                last_message = message_text,
                reason = "Customer explicity requested a human agent",
                conversation_id= conversation_id,
            )
            await send_whatsapp_message(from_number, "I'll connect you with a human agent right away. Please wait — someone from our team will be with you shortly.")

            return {"status" : "ok"}

        # normal rag flow

        chat_history = await get_chat_history(conversation_id)
        long_term_summary = await get_conversation_summary(conversation_id)

        rag_result = run_rag_pipeline(
            question = message_text,
            chat_history = chat_history,
            long_term_summary = long_term_summary,
        )
        answer = rag_result["answer"]

        current_sentiment = analyze(message_text)
        await save_message(
            conversation_id = conversation_id,
            role = "user",
            sentiment_score = current_sentiment["score"],
            sentiment_label = current_sentiment["label"],
            rag_used = True,
            cache_hit = False,
        )

        sentiment_history = await get_sentiment_history(conversation_id)
        escalation = check_escalation(sentiment_history)

        if escalation["should_escalate"]:
            await mark_escalated(conversation_id, escalation["reason"])
            await send_slack_alert(
                chat_id= from_number,
                customer_name = customer_name,
                last_message = message_text,
                reason = escalation["reason"],
                conversation_id= conversation_id,
            )
            answer = "Our support team has been notified. A human agent will be with you shortly. Please wait."

        await save_message(
            conversation_id = conversation_id,
            role = "assistant",
            content = answer,
        )
        await send_whatsapp_message(from_number, answer)
        return {"status" : "ok"}

    except Exception as e:
        logger.error(f"Error processing WhatsApp webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    # hitl gate
    conv_status = await get_conversation_status(conversation_id)
    if conv_status == "escalated":
        timed_out, human_replied = await check_escalation_timeout(conversation_id, timeout_minutes=5)
        if human_replied:
            logger.info("Human agent active - bot stays paused")
            return ChatResponse(
                answer = "A human is handling your case. Please wait..",
                escalated = True,
                cache_hit = False,
                sentiment_label = "neutral",
                sentiment_score = 0.0,
                conversation_id = conversation_id,
            )
        elif not timed_out:
            logger.info("Waiting for human agent (within timeout)")
            return ChatResponse(
                answer = (
                    "Our support team has been notified. A human agent will be with you shortly. Please wait."
                ),
                escalated = True,
                cache_hit = False,
                sentiment_label = "neutral",
                sentiment_score = 0.0,
                conversation_id = conversation_id,
            )

        else:
            logger.info("Escalation timed out - bot resuming")
            await auto_resolve_conversation(conversation_id)


    HUMAN_REQUEST_PHRASES = [
    "talk to agent",     "talk to human",    "talk to a human",
    "real person",       "human agent",      "connect me to",
    "transfer me",       "speak to someone", "i want a human",
    "need a human",      "get me a human",   "want to speak",
    "want to talk to",   "actual person",    "live agent",
    "speak to a person", "speak to agent",   "to an agent",
    "to a human",        "to a human agent", "to a real person",
    "to a live agent",   "to a support agent","to a support person",
    "to a support representative", "to a customer service agent",
    "to a customer service representative", "to a customer support agent",
    "to a customer support representative", "to a customer care agent",
    "to a customer care representative", "to a technical support agent",
    "to a technical support representative", "to a help desk agent",
    "to a help desk representative", "to a service desk agent",
    "to a service desk representative", "to a support specialist",
    "to a customer service specialist", "to a customer support specialist",
    "to a customer care specialist", "to a technical support specialist",
    "to a help desk specialist", "to a service desk specialist", "to a support representative", "to a customer service representative",
    "to a customer support representative", "to a customer care representative", "to a technical support representative", "to a help desk representative",
    "to a service desk representative", "to a support agent", "to a customer service agent", "to a customer support agent", "to a customer care agent", "to a technical support agent",
    "to a help desk agent", "to a service desk agent", "to a support specialist", "to a customer service specialist", "to a customer support specialist", "to a customer care specialist", "to a technical support specialist", "to a help desk specialist", "to a service desk specialist", "to a support representative", "to a customer service representative", "to a customer support representative", "to a customer care representative", "to a technical support representative", "to a help desk representative", "to a service desk representative"
    ]

    if any(phrase in request.message.lower() for phrase in HUMAN_REQUEST_PHRASES):
        logger.info(f"Explicit human request from: {request.telegram_chat_id}")
        await mark_escalated(conversation_id, "Customer explicitly requested a human agent")
        await send_slack_alert(
            chat_id=request.telegram_chat_id,
            customer_name=request.customer_name,
            last_message=request.message,
            reason="Customer explicitly requested a human agent",
        )
        return ChatResponse(
            answer=(
                "I'll connect you with a human agent right away. Please wait — someone from our team will be with you shortly."
            ),
            escalated=True,
            cache_hit=False,
            sentiment_label="neutral",
            sentiment_score=0.0,
        )

    # step 2: check cache
    long_term_summary = await get_conversation_summary(conversation_id)

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
                long_term_summary=long_term_summary,
            )
        answer = rag_result["answer"]
        await set_cache(request.message, answer)

    # step 4: analyze sentiment of current message
    current_sentiment = analyze(request.message)
    response_ms = int((time.time() - start_time) * 1000)

    total_msgs = await get_total_message_count(conversation_id)
    if total_msgs > 0 and total_msgs % 10 == 0:
        logger.info(f"Summarizing conversation {conversation_id} after {total_msgs} messages")
        messages_to_summarize = await get_messages_for_summary(conversation_id)
        new_summary = summarize_conversation(messages_to_summarize)
        if new_summary:
            await update_conversation_summary(conversation_id, new_summary)

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
        long_term_summary=long_term_summary,
    )

@app.post("/resolve/{conversation_id}")
async def resolve_conversation(conversation_id: str):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM conversations where id = $1::uuid", conversation_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Conversation not found")
        await conn.execute(
            "UPDATE conversations SET status = 'resolved' WHERE id = $1::uuid",
            conversation_id,
        )
        await conn.execute(
            "UPDATE escalations SET resolved = true, resolved_at = NOW() WHERE conversation_id = $1::uuid AND resolved = false",
            conversation_id,
        )
    logger.info(f"Conversation {conversation_id} resolved")
    return {
        "status" : "resolved",
        "conversation_id" : conversation_id.capitalize(),
        "message" : "Bot will now resume answering messages.",
    }

@app.post("/human_reply")
async def human_reply(request: HumanReplyRequest):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM conversations where id = $1::uuid", request.conversation_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Conversation not found")
    content = (
        f"[{request.agent_name}]: {request.message}"
        if request.agent_name
        else request.message
    )

    await save_message(
        conversation_id=request.conversation_id,
        role="human_agent",
        content=content,

    )

    logger.info(f"Human agent reply saved for conversation {request.conversation_id}")
    return {
        "status" : "ok",
        "conversation_id" : request.conversation_id,
                }

@app.get("/messages/{conversation_id}")
async def get_messages(conversation_id: str, limit: int = 20):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT role, content, created_at FROM messages
               WHERE conversation_id = $1
               ORDER BY created_at ASC LIMIT $2""",
            conversation_id,
            limit,
        )
    return {
        "conversation_id" : conversation_id,
        "messages" : [
            {
                "role" : r["role"],
                "content" : r["content"],
                "created_at" : r["created_at"].isoformat(),
            }
            for r in rows
        ],
    }

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