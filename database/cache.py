from loguru import logger

from api.metrics import CACHE_HITS, CACHE_MISSES
from database.pool import get_redis


async def get_cache(key: str) -> str | None:
    try:
        cached = await get_redis().get(f"cache:{key}")
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
        await get_redis().setex(f"cache:{key}", ttl, value)
        logger.debug(f"Cached: {key[:50]}")
    except Exception as e:
        logger.warning(f"Cache set failed: {e}")
