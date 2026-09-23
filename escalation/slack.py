import os

import httpx
from loguru import logger

from database.messages import save_message


async def send_slack_alert(
    conversation_id: str,
    chat_id: str,
    customer_name: str | None,
    last_message: str,
    reason: str,
) -> None:
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("No Slack webhook configured")
        return

    name = customer_name or chat_id
    payload = {
        "text": (
            f"🚨 *Escalation Alert*\n"
            f"*Customer:* {name}\n"
            f"*Reason:* {reason}\n"
            f"*Last message:* {last_message[:200]}\n"
            f"*Conversation ID:* {conversation_id}\n\n"
            f"*To reply:* paste this in thread:\n"
            f"{conversation_id} | your message here\n\n"
            f"*To resolve:* paste this in thread:\n"
            f"{conversation_id} | resolved"
        )
    }

    async with httpx.AsyncClient() as client:
        try:
            await client.post(webhook_url, json=payload, timeout=5)
            logger.info(f"Slack alert sent for: {chat_id}")
        except Exception as e:
            logger.error(f"Slack alert failed: {e}")


async def forward_to_agent(
    conversation_id: str,
    chat_id: str,
    customer_name: str | None,
    message: str,
) -> None:
    """Save a customer message sent during an escalation and post it to Slack for the agent."""
    await save_message(conversation_id=conversation_id, role="user", content=message)

    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("No Slack webhook configured")
        return

    name = customer_name or chat_id
    payload = {
        "text": (
            f"💬 *Customer message* from {name}\n"
            f">{message[:500]}\n"
            f"*Conversation ID:* {conversation_id}\n"
            f"*To reply:* paste this in thread:\n"
            f"{conversation_id} | your message here"
        )
    }

    async with httpx.AsyncClient() as client:
        try:
            await client.post(webhook_url, json=payload, timeout=5)
            logger.info(f"Customer message forwarded to Slack for: {chat_id}")
        except Exception as e:
            logger.error(f"Forwarding to Slack failed: {e}")
