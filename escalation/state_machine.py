from dataclasses import dataclass

from loguru import logger

from api.metrics import ESCALATIONS_TOTAL
from database.conversations import get_conversation_status
from database.escalations import auto_resolve_conversation, check_escalation_timeout, mark_escalated
from escalation.phrases import is_explicit_human_request
from escalation.sentiment_gate import check_consecutive_negatives
from escalation.slack import forward_to_agent, send_slack_alert

WAITING_MESSAGE = "Our support team has been notified. A human agent will be with you shortly. Please wait."
FORWARDED_MESSAGE = "✅ Your message has been sent to our support agent."
EXPLICIT_HANDOFF_MESSAGE = (
    "I'll connect you with a human agent right away. "
    "Please wait — someone from our team will be with you shortly."
)


@dataclass
class GateOutcome:
    """Result of checking the human-in-the-loop gate before running the bot."""

    intercepted: bool
    answer: str | None = None


async def hitl_gate(
    conversation_id: str,
    chat_id: str,
    customer_name: str | None,
    message: str,
) -> GateOutcome:
    """If a conversation is already escalated, decide whether the bot should
    stay paused (forwarding the message to the human agent) or resume.
    """
    status = await get_conversation_status(conversation_id)
    if status != "escalated":
        return GateOutcome(intercepted=False)

    timed_out, human_replied = await check_escalation_timeout(conversation_id, timeout_minutes=5)

    if human_replied:
        logger.info("Human agent active - forwarding customer message to agent")
        await forward_to_agent(
            conversation_id=conversation_id,
            chat_id=chat_id,
            customer_name=customer_name,
            message=message,
        )
        return GateOutcome(intercepted=True, answer=FORWARDED_MESSAGE)

    if not timed_out:
        logger.info("Waiting for human agent (within timeout) - forwarding message")
        await forward_to_agent(
            conversation_id=conversation_id,
            chat_id=chat_id,
            customer_name=customer_name,
            message=message,
        )
        return GateOutcome(intercepted=True, answer=WAITING_MESSAGE)

    logger.info("Escalation timed out - bot resuming")
    await auto_resolve_conversation(conversation_id)
    return GateOutcome(intercepted=False)


async def handle_explicit_request(
    conversation_id: str,
    chat_id: str,
    customer_name: str | None,
    message: str,
) -> str | None:
    """If the customer explicitly asked for a human, escalate and return the
    handoff message. Returns None if no explicit request was made."""
    if not is_explicit_human_request(message):
        return None

    logger.info(f"Explicit human request from: {chat_id}")
    await mark_escalated(conversation_id, "Customer explicitly requested a human agent")
    await send_slack_alert(
        conversation_id=conversation_id,
        chat_id=chat_id,
        customer_name=customer_name,
        last_message=message,
        reason="Customer explicitly requested a human agent",
    )
    return EXPLICIT_HANDOFF_MESSAGE


async def evaluate_sentiment_escalation(
    conversation_id: str,
    chat_id: str,
    customer_name: str | None,
    message: str,
    sentiment_history: list[dict],
) -> dict:
    """Checks consecutive-negative sentiment history and escalates (marking the
    conversation + alerting Slack) if the 3-strike threshold is crossed."""
    escalation = check_consecutive_negatives(sentiment_history)

    if escalation["should_escalate"]:
        ESCALATIONS_TOTAL.inc()
        await mark_escalated(conversation_id, escalation["reason"])
        await send_slack_alert(
            conversation_id=conversation_id,
            chat_id=chat_id,
            customer_name=customer_name,
            last_message=message,
            reason=escalation["reason"],
        )

    return escalation
