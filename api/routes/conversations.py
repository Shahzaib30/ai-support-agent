from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from database.conversations import (
    conversation_exists,
    get_conversation_by_chat_id,
    resolve_conversation,
)
from database.messages import get_messages, save_message

router = APIRouter()


class HumanReplyRequest(BaseModel):
    conversation_id: str
    message: str
    agent_name: str | None = None


@router.post("/resolve/{conversation_id}")
async def resolve(conversation_id: str):
    found = await resolve_conversation(conversation_id)
    if not found:
        raise HTTPException(status_code=404, detail="Conversation not found")

    logger.info(f"Conversation {conversation_id} resolved")
    return {
        "status": "resolved",
        "conversation_id": conversation_id,
        "message": "Bot will now resume answering messages.",
    }


@router.post("/human_reply")
async def human_reply(request: HumanReplyRequest):
    if not await conversation_exists(request.conversation_id):
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
    return {"status": "ok", "conversation_id": request.conversation_id}


@router.get("/messages/{conversation_id}")
async def list_messages(conversation_id: str, limit: int = 100):
    return {
        "conversation_id": conversation_id,
        "messages": await get_messages(conversation_id, limit),
    }


@router.get("/conversation/{telegram_chat_id}")
async def conversation_by_chat_id(telegram_chat_id: str):
    logger.debug(f"Looking up conversation for: {telegram_chat_id}")
    result = await get_conversation_by_chat_id(telegram_chat_id)
    if not result:
        return {"conversation_id": None, "status": None}
    return result
