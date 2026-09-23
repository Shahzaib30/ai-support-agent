from loguru import logger

from database.pool import get_pool


async def check_and_record(source: str, event_id: str) -> bool:
    """
    Records (source, event_id) as processed. Returns True if this is the
    first time it's been seen, False if it's a duplicate (e.g. a retried
    WhatsApp/Telegram webhook delivery or a retried Slack Events callback).

    Callers should skip processing entirely when this returns False.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO processed_events (source, event_id)
               VALUES ($1, $2)
               ON CONFLICT (source, event_id) DO NOTHING
               RETURNING id""",
            source,
            event_id,
        )
    is_new = row is not None
    if not is_new:
        logger.info(f"Duplicate event skipped: source={source} event_id={event_id}")
    return is_new
