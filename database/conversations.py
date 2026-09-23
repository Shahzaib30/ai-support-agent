from loguru import logger

from api.metrics import ACTIVE_CONVERSATIONS
from database.pool import get_pool


async def get_or_create_conversation(chat_id: str, customer_name: str | None) -> str:
    pool = get_pool()
    async with pool.acquire() as conn:
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


async def get_conversation_status(conversation_id: str) -> str:
    pool = get_pool()
    async with pool.acquire() as conn:
        status = await conn.fetchval(
            "SELECT status FROM conversations WHERE id = $1",
            conversation_id,
        )
    return status or "active"


async def get_conversation_by_chat_id(chat_id: str) -> dict | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, status FROM conversations WHERE telegram_chat_id = $1",
            chat_id,
        )
    if not row:
        return None
    return {"conversation_id": str(row["id"]), "status": row["status"]}


async def get_conversation_summary(conversation_id: str) -> str:
    pool = get_pool()
    async with pool.acquire() as conn:
        summary = await conn.fetchval(
            "SELECT summary FROM conversations WHERE id = $1",
            conversation_id,
        )
        return summary or ""


async def update_conversation_summary(conversation_id: str, summary: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE conversations SET summary = $1 WHERE id = $2",
            summary,
            conversation_id,
        )
        logger.info(f"Updated conversation {conversation_id} summary: {summary[:80]}...")


async def resolve_conversation(conversation_id: str) -> bool:
    """Marks a conversation resolved and closes any open escalation.
    Returns False if the conversation does not exist."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM conversations WHERE id = $1::uuid", conversation_id
        )
        if not row:
            return False
        await conn.execute(
            "UPDATE conversations SET status = 'resolved' WHERE id = $1::uuid",
            conversation_id,
        )
        await conn.execute(
            """UPDATE escalations SET resolved = true, resolved_at = NOW()
               WHERE conversation_id = $1::uuid AND resolved = false""",
            conversation_id,
        )
    return True


async def conversation_exists(conversation_id: str) -> bool:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM conversations WHERE id = $1::uuid", conversation_id
        )
    return row is not None


async def restore_active_conversation_count() -> int:
    pool = get_pool()
    count = await pool.fetchval("SELECT COUNT(*) FROM conversations")
    ACTIVE_CONVERSATIONS.set(count or 0)
    return count or 0
