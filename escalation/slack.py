import os

import httpx
from loguru import logger

from connectors.base import IncomingMessage
from database.escalations import get_slack_thread_ts, set_slack_thread_ts
from database.messages import save_message

SLACK_API_URL = "https://slack.com/api/chat.postMessage"


def _slack_configured() -> tuple[str | None, str | None]:
    token = os.getenv("SLACK_BOT_TOKEN")
    channel = os.getenv("SLACK_CHANNEL_ID")
    if not token or not channel:
        logger.warning("Slack not configured (SLACK_BOT_TOKEN/SLACK_CHANNEL_ID missing)")
        return None, None
    return token, channel


async def _post_to_slack(payload: dict) -> dict | None:
    token, channel = _slack_configured()
    if not token:
        return None

    payload = {"channel": channel, **payload}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                SLACK_API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=5,
            )
            data = response.json()
            if not data.get("ok"):
                logger.error(f"Slack API error: {data.get('error')}")
                return None
            return data
        except Exception as e:
            logger.error(f"Slack request failed: {e}")
            return None


def _build_escalation_blocks(msg: IncomingMessage, reason: str, sentiment: dict | None) -> list[dict]:
    customer = msg.customer_name or msg.customer_id
    sentiment_line = ""
    if sentiment:
        sentiment_line = f"\n*Sentiment:* {sentiment.get('label', 'unknown')} ({sentiment.get('score', 0):+.2f})"

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"🚨 *Escalation — human assistance needed*\n"
                    f"*Customer:* {customer}\n"
                    f"*Channel:* {msg.channel}\n"
                    f"*Reason:* {reason}"
                    f"{sentiment_line}\n"
                    f"*Message:* {msg.message[:500]}"
                ),
            },
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"Conversation ID: `{msg.conversation_id}`"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*To respond:* just reply in this thread — no special format needed.\n"
                    "*To hand back to the bot:* reply `resolved` in this thread."
                ),
            },
        },
    ]


async def send_slack_alert(msg: IncomingMessage, reason: str, sentiment: dict | None = None) -> None:
    """
    Posts a new escalation alert to the support Slack channel. The message
    carries the conversation id both visibly (for humans) and as structured
    Slack message metadata (for Workflow B to resolve thread replies back to
    this conversation without anyone typing a UUID).
    """
    payload = {
        "text": f"Escalation for {msg.customer_name or msg.customer_id} ({msg.channel}): {reason}",
        "blocks": _build_escalation_blocks(msg, reason, sentiment),
        "metadata": {
            "event_type": "support_escalation",
            "event_payload": {
                "conversation_id": msg.conversation_id,
                "channel": msg.channel,
                "customer_id": msg.customer_id,
            },
        },
    }

    result = await _post_to_slack(payload)
    if result:
        await set_slack_thread_ts(msg.conversation_id, result["ts"])
        logger.info(f"Slack escalation alert sent for conversation {msg.conversation_id}")


async def forward_to_agent(msg: IncomingMessage) -> None:
    """Saves a customer message sent while a conversation is escalated, and
    (if we have a thread to post into) relays it as a threaded reply under
    the original escalation alert so the agent sees it without switching
    channels."""
    await save_message(conversation_id=msg.conversation_id, role="user", content=msg.message)

    thread_ts = await get_slack_thread_ts(msg.conversation_id)
    if not thread_ts:
        return

    customer = msg.customer_name or msg.customer_id
    await _post_to_slack({
        "thread_ts": thread_ts,
        "text": f"💬 *{customer}:* {msg.message[:500]}",
    })
