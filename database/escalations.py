from datetime import datetime, timezone

from loguru import logger

from database.pool import get_pool


async def mark_escalated(conversation_id: str, reason: str) -> None:
    """Entry point for a new escalation (explicit request, sentiment 3-strike,
    or low RAG confidence). Moves the conversation to human_pending."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE conversations
               SET is_escalated = true, escalated_at = NOW(), status = 'human_pending'
               WHERE id = $1""",
            conversation_id,
        )
        await conn.execute(
            """INSERT INTO escalations (conversation_id, reason, slack_notified)
               VALUES ($1, $2, true)""",
            conversation_id,
            reason,
        )


async def mark_human_active(conversation_id: str) -> None:
    """Called when a human agent actually replies (`/human_reply`). Distinct
    from mark_escalated: human_pending means "waiting", human_active means
    "someone is engaged" — once active, the auto-resume timeout no longer
    applies, and only a manual /resolve returns the conversation to the bot."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE conversations SET status = 'human_active' WHERE id = $1",
            conversation_id,
        )


async def escalation_pending_timed_out(conversation_id: str, timeout_minutes: int = 5) -> bool:
    """True if the conversation has been sitting in human_pending (no agent
    has engaged yet) longer than timeout_minutes."""
    pool = get_pool()
    async with pool.acquire() as conn:
        escalated_at = await conn.fetchval(
            "SELECT escalated_at FROM conversations WHERE id = $1",
            conversation_id,
        )

    if not escalated_at:
        return False

    now = datetime.now(timezone.utc)
    elapsed = (now - escalated_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
    timed_out = elapsed > timeout_minutes

    logger.info(f"human_pending check: {elapsed:.1f} min elapsed | timed_out={timed_out}")
    return timed_out


async def set_slack_thread_ts(conversation_id: str, slack_ts: str) -> None:
    """Records the Slack message ts of the escalation alert on its (most
    recent, unresolved) escalations row, so later customer follow-ups can be
    threaded under it."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE escalations SET slack_message_ts = $1
               WHERE id = (
                   SELECT id FROM escalations
                   WHERE conversation_id = $2 AND resolved = false
                   ORDER BY created_at DESC LIMIT 1
               )""",
            slack_ts,
            conversation_id,
        )


async def get_slack_thread_ts(conversation_id: str) -> str | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """SELECT slack_message_ts FROM escalations
               WHERE conversation_id = $1 AND resolved = false
               ORDER BY created_at DESC LIMIT 1""",
            conversation_id,
        )


async def auto_resolve_conversation(conversation_id: str) -> None:
    """Auto-resume the bot after a human_pending timeout with no agent
    engagement. Never called once a conversation is human_active."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE conversations
               SET status = 'ai_active', is_escalated = false
               WHERE id = $1""",
            conversation_id,
        )
        await conn.execute(
            """UPDATE escalations
               SET resolved = true, resolved_at = NOW()
               WHERE conversation_id = $1 AND resolved = false""",
            conversation_id,
        )
        logger.info(f"Auto-resumed after human_pending timeout: {conversation_id}")
