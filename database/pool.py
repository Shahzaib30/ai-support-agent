import os

import asyncpg
import redis.asyncio as aioredis
from loguru import logger

db_pool: asyncpg.Pool | None = None
redis_client: aioredis.Redis | None = None


async def connect() -> None:
    global db_pool, redis_client

    db_pool = await asyncpg.create_pool(
        dsn=os.getenv("DATABASE_URL"),
        min_size=2,
        max_size=10,
    )
    logger.success("Database connection pool created")

    redis_client = aioredis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379"),
        encoding="utf-8",
        decode_responses=True,
    )
    logger.success("Redis connection established")


async def disconnect() -> None:
    if db_pool is not None:
        await db_pool.close()
    if redis_client is not None:
        await redis_client.close()
    logger.info("Database and Redis connections closed")


def get_pool() -> asyncpg.Pool:
    if db_pool is None:
        raise RuntimeError("Database pool is not initialized — call database.pool.connect() first")
    return db_pool


def get_redis() -> aioredis.Redis:
    if redis_client is None:
        raise RuntimeError("Redis client is not initialized — call database.pool.connect() first")
    return redis_client
