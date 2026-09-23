from database.pool import get_pool


def _normalize_role(role: str) -> str:
    return "assistant" if role == "human_agent" else role


async def save_message(
    conversation_id: str,
    role: str,
    content: str,
    sentiment_score: float | None = None,
    sentiment_label: str | None = None,
    rag_used: bool = False,
    cache_hit: bool = False,
    response_ms: int | None = None,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO messages
               (conversation_id, role, content, sentiment_score,
                sentiment_label, rag_used, cache_hit, response_time_ms)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
            conversation_id, role, content,
            sentiment_score, sentiment_label,
            rag_used, cache_hit, response_ms,
        )


async def get_chat_history(conversation_id: str, limit: int = 6) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT role, content FROM messages
               WHERE conversation_id = $1
               ORDER BY created_at DESC LIMIT $2""",
            conversation_id,
            limit,
        )
    return [
        {"role": _normalize_role(r["role"]), "content": r["content"]}
        for r in reversed(rows)
    ]


async def get_sentiment_history(conversation_id: str, limit: int = 10) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT sentiment_label, sentiment_score
               FROM messages
               WHERE conversation_id = $1
               AND role = 'user'
               AND sentiment_label IS NOT NULL
               ORDER BY created_at DESC LIMIT $2""",
            conversation_id,
            limit,
        )
    result = [{"label": r["sentiment_label"], "score": r["sentiment_score"]} for r in rows]
    return list(reversed(result))


async def get_messages_for_summary(conversation_id: str, limit: int = 20) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT role, content FROM messages
               WHERE conversation_id = $1
               ORDER BY created_at DESC LIMIT $2""",
            conversation_id,
            limit,
        )
    return [
        {"role": _normalize_role(r["role"]), "content": r["content"]}
        for r in reversed(rows)
    ]


async def get_total_message_count(conversation_id: str) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = $1",
            conversation_id,
        )
    return count or 0


async def get_messages(conversation_id: str, limit: int = 100) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT role, content, created_at FROM messages
               WHERE conversation_id = $1
               ORDER BY created_at ASC LIMIT $2""",
            conversation_id,
            limit,
        )
    return [
        {
            "role": r["role"],
            "content": r["content"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]
