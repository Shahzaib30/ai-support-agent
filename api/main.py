import os
import json
import httpx
import asyncpg
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
