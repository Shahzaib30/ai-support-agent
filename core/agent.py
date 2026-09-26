import time

from loguru import logger

from api.metrics import MESSAGES_TOTAL, RESPONSE_TIME
from connectors.base import AgentReply, IncomingMessage
from database.cache import get_cache, set_cache
from database.conversations import (
    get_conversation_summary,
    get_or_create_conversation,
    update_conversation_summary,
)
from database.escalations import mark_escalated
from database.idempotency import check_and_record
from database.messages import (
    get_chat_history,
    get_messages_for_summary,
    get_sentiment_history,
    get_total_message_count,
    save_message,
)
from escalation.slack import send_slack_alert
from escalation.state_machine import (
    evaluate_sentiment_escalation,
    handle_explicit_request,
    hitl_gate,
)
from rag.chain import run_rag_pipeline, summarize_conversation
from sentiment.analyzer import analyze

SUMMARIZE_EVERY_N_MESSAGES = 10


def _early_reply(answer: str, conversation_id: str, escalated: bool = True) -> AgentReply:
    return AgentReply(
        answer=answer,
        escalated=escalated,
        cache_hit=False,
        sentiment_label="neutral",
        sentiment_score=0.0,
        conversation_id=conversation_id,
    )


async def process_message(msg: IncomingMessage) -> AgentReply:
    """
    The single, channel-agnostic entrypoint every connector funnels normalized
    inbound messages through: idempotency, conversation bookkeeping, the
    human-handoff gate, RAG generation, sentiment tracking, and escalation.
    """
    event_id = msg.metadata.get("event_id")
    if event_id and not await check_and_record(source=msg.channel, event_id=event_id):
        # Retried webhook delivery (WhatsApp/Telegram at-least-once semantics)
        # for a message we've already processed — do nothing, no reply needed.
        return _early_reply("", conversation_id="", escalated=False)

    start_time = time.time()
    MESSAGES_TOTAL.inc()
    logger.info(f"[{msg.channel}] message from {msg.customer_id}")

    msg.conversation_id = await get_or_create_conversation(msg.customer_id, msg.customer_name, msg.channel)

    gate = await hitl_gate(msg)
    if gate.intercepted:
        return _early_reply(gate.answer, msg.conversation_id)

    explicit_answer = await handle_explicit_request(msg)
    if explicit_answer:
        return _early_reply(explicit_answer, msg.conversation_id)

    long_term_summary = await get_conversation_summary(msg.conversation_id)

    cache_hit = False
    low_confidence = False
    answer = await get_cache(msg.message)

    if answer:
        cache_hit = True
        logger.info("Served from cache")
    else:
        chat_history = await get_chat_history(msg.conversation_id)
        with RESPONSE_TIME.time():
            rag_result = await run_rag_pipeline(
                question=msg.message,
                chat_history=chat_history,
                long_term_summary=long_term_summary,
            )
        answer = rag_result["answer"]
        low_confidence = rag_result.get("low_confidence", False)
        if not low_confidence:
            await set_cache(msg.message, answer)

    current_sentiment = await analyze(msg.message)
    response_ms = int((time.time() - start_time) * 1000)

    total_msgs = await get_total_message_count(msg.conversation_id)
    if total_msgs > 0 and total_msgs % SUMMARIZE_EVERY_N_MESSAGES == 0:
        logger.info(f"Summarizing conversation {msg.conversation_id} after {total_msgs} messages")
        messages_to_summarize = await get_messages_for_summary(msg.conversation_id)
        new_summary = await summarize_conversation(messages_to_summarize)
        if new_summary:
            await update_conversation_summary(msg.conversation_id, new_summary)

    await save_message(
        conversation_id=msg.conversation_id,
        role="user",
        content=msg.message,
        sentiment_score=current_sentiment["score"],
        sentiment_label=current_sentiment["label"],
        rag_used=not cache_hit,
        cache_hit=cache_hit,
        response_ms=response_ms,
    )

    sentiment_history = await get_sentiment_history(msg.conversation_id)
    escalation = await evaluate_sentiment_escalation(msg, sentiment_history)
    escalated = escalation["should_escalate"]


    await save_message(
        conversation_id=msg.conversation_id,
        role="assistant",
        content=answer,
    )

    logger.success(
        f"Done in {response_ms}ms — "
        f"sentiment: {current_sentiment['label']} ({current_sentiment['score']}) — "
        f"consecutive negatives: {escalation['consecutive_negatives']} — "
        f"escalated: {escalated}"
    )

    return AgentReply(
        answer=answer,
        escalated=escalated,
        cache_hit=cache_hit,
        sentiment_label=current_sentiment["label"],
        sentiment_score=current_sentiment["score"],
        conversation_id=msg.conversation_id,
    )
