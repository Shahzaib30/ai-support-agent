from database.pool import get_pool


async def get_today_stats() -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
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
        "total_messages": total_msgs,
        "total_conversations": stats["total_conversations"] or 0,
        "total_escalations": escalations or 0,
        "avg_sentiment": round(float(stats["avg_sentiment"] or 0), 2),
        "avg_response_ms": round(float(stats["avg_response_ms"] or 0)),
        "cache_hit_rate": round((cache_hits / total_msgs * 100) if total_msgs > 0 else 0, 1),
    }
