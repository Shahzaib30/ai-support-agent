from datetime import datetime, timezone

from loguru import logger

from database.pool import get_pool


async def mark_escalated(conversation_id: str, reason: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
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


async def check_escalation_timeout(conversation_id: str, timeout_minutes: int = 5) -> tuple[bool, bool]:
    """Returns (timed_out, human_replied)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT escalated_at,
            EXISTS(
                SELECT 1 FROM messages
                WHERE conversation_id = $1
                AND role = 'human_agent')
                as human_replied
                FROM conversations
                WHERE id = $1""",
            conversation_id,
        )

        if not row or not row["escalated_at"]:
            return False, False

        now = datetime.now(timezone.utc)
        escalated_at = row["escalated_at"].replace(tzinfo=timezone.utc)
        elapsed = (now - escalated_at).total_seconds() / 60

        timed_out = elapsed > timeout_minutes
        human_replied = row["human_replied"]

        logger.info(
            f"Escalation check: {elapsed:.1f} min elapsed | "
            f"human_replied = {human_replied} | timed_out = {timed_out}"
        )
        return timed_out, human_replied


async def auto_resolve_conversation(conversation_id: str) -> None:
    """Auto-resolve an escalation after timeout — resumes the bot."""
    pool = get_pool()
    async with pool.acquire() as conn:
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
