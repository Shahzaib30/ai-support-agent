from dataclasses import dataclass

from loguru import logger

from api.metrics import ESCALATIONS_TOTAL
from connectors.base import IncomingMessage
from database.conversations import get_conversation_status
from database.escalations import auto_resolve_conversation, escalation_pending_timed_out, mark_escalated
from escalation.phrases import is_explicit_human_request
from escalation.sentiment_gate import check_consecutive_negatives
from escalation.slack import forward_to_agent, send_slack_alert

WAITING_MESSAGE = "Our support team has been notified. A human agent will be with you shortly. Please wait."
FORWARDED_MESSAGE = "✅ Your message has been sent to our support agent."
EXPLICIT_HANDOFF_MESSAGE = (
    "I'll connect you with a human agent right away. "
    "Please wait — someone from our team will be with you shortly."
)

HUMAN_PENDING_TIMEOUT_MINUTES = 5


@dataclass
class GateOutcome:
    """Result of checking the human-in-the-loop gate before running the bot."""

    intercepted: bool
    answer: str | None = None


async def hitl_gate(msg: IncomingMessage) -> GateOutcome:
    """
    Reads the conversation's explicit lifecycle state and decides whether the
    bot should stay paused (forwarding the message to the human agent) or
    resume answering.

    ai_active                -> bot answers normally (not intercepted)
    human_pending, not timed out -> forward to agent, tell customer to wait
    human_pending, timed out  -> nobody engaged in time; auto-resume the bot
    human_active              -> an agent is engaged; always forward, never
                                  auto-times-out (only a manual /resolve exits)
    resolved / closed         -> bot answers normally (not intercepted)
    """
    status = await get_conversation_status(msg.conversation_id)

    if status == "human_active":
        logger.info("Human agent active - forwarding customer message to agent")
        await forward_to_agent(msg)
        return GateOutcome(intercepted=True, answer=FORWARDED_MESSAGE)

    if status == "human_pending":
        timed_out = await escalation_pending_timed_out(msg.conversation_id, HUMAN_PENDING_TIMEOUT_MINUTES)
        if not timed_out:
            logger.info("Waiting for human agent (within timeout) - forwarding message")
            await forward_to_agent(msg)
            return GateOutcome(intercepted=True, answer=WAITING_MESSAGE)

        logger.info("human_pending timed out with no agent engagement - bot resuming")
        await auto_resolve_conversation(msg.conversation_id)
        return GateOutcome(intercepted=False)

    return GateOutcome(intercepted=False)


async def handle_explicit_request(msg: IncomingMessage) -> str | None:
    """If the customer explicitly asked for a human, escalate and return the
    handoff message. Returns None if no explicit request was made."""
    if not is_explicit_human_request(msg.message):
        return None

    logger.info(f"Explicit human request from: {msg.customer_id}")
    await mark_escalated(msg.conversation_id, "Customer explicitly requested a human agent")
    await send_slack_alert(msg, reason="Customer explicitly requested a human agent")
    return EXPLICIT_HANDOFF_MESSAGE


async def evaluate_sentiment_escalation(
    msg: IncomingMessage,
    sentiment_history: list[dict],
) -> dict:
    """Checks consecutive-negative sentiment history and escalates (marking the
    conversation + alerting Slack) if the 3-strike threshold is crossed."""
    escalation = check_consecutive_negatives(sentiment_history)

    if escalation["should_escalate"]:
        ESCALATIONS_TOTAL.inc()
        current_sentiment = sentiment_history[-1] if sentiment_history else None
        await mark_escalated(msg.conversation_id, escalation["reason"])
        await send_slack_alert(msg, reason=escalation["reason"], sentiment=current_sentiment)

    return escalation
