import time

from loguru import logger

from api.metrics import MESSAGES_TOTAL, RESPONSE_TIME
from connectors.base import AgentReply, InboundMessage
from database.cache import get_cache, set_cache
from database.conversations import (
    get_conversation_summary,
    get_or_create_conversation,
    update_conversation_summary,
)
from database.escalations import mark_escalated
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


async def process_message(msg: InboundMessage) -> AgentReply:
    """
    The single, channel-agnostic entrypoint every connector funnels normalized
    inbound messages through: conversation bookkeeping, the human-handoff gate,
    RAG generation, sentiment tracking, and 3-strike escalation.
    """
    start_time = time.time()
    MESSAGES_TOTAL.inc()
    logger.info(f"[{msg.channel}] message from {msg.external_id}")

    conversation_id = await get_or_create_conversation(msg.external_id, msg.customer_name)

    gate = await hitl_gate(conversation_id, msg.external_id, msg.customer_name, msg.text)
    if gate.intercepted:
        return AgentReply(
            answer=gate.answer,
            escalated=True,
            cache_hit=False,
            sentiment_label="neutral",
            sentiment_score=0.0,
            conversation_id=conversation_id,
        )

    explicit_answer = await handle_explicit_request(
        conversation_id, msg.external_id, msg.customer_name, msg.text
    )
    if explicit_answer:
        return AgentReply(
            answer=explicit_answer,
            escalated=True,
            cache_hit=False,
            sentiment_label="neutral",
            sentiment_score=0.0,
            conversation_id=conversation_id,
        )

    long_term_summary = await get_conversation_summary(conversation_id)

    cache_hit = False
    low_confidence = False
    answer = await get_cache(msg.text)

    if answer:
        cache_hit = True
        logger.info("Served from cache")
    else:
        chat_history = await get_chat_history(conversation_id)
        with RESPONSE_TIME.time():
            rag_result = await run_rag_pipeline(
                question=msg.text,
                chat_history=chat_history,
                long_term_summary=long_term_summary,
            )
        answer = rag_result["answer"]
        low_confidence = rag_result.get("low_confidence", False)
        if not low_confidence:
            await set_cache(msg.text, answer)

    current_sentiment = await analyze(msg.text)
    response_ms = int((time.time() - start_time) * 1000)

    total_msgs = await get_total_message_count(conversation_id)
    if total_msgs > 0 and total_msgs % SUMMARIZE_EVERY_N_MESSAGES == 0:
        logger.info(f"Summarizing conversation {conversation_id} after {total_msgs} messages")
        messages_to_summarize = await get_messages_for_summary(conversation_id)
        new_summary = await summarize_conversation(messages_to_summarize)
        if new_summary:
            await update_conversation_summary(conversation_id, new_summary)

    await save_message(
        conversation_id=conversation_id,
        role="user",
        content=msg.text,
        sentiment_score=current_sentiment["score"],
        sentiment_label=current_sentiment["label"],
        rag_used=not cache_hit,
        cache_hit=cache_hit,
        response_ms=response_ms,
    )

    sentiment_history = await get_sentiment_history(conversation_id)
    escalation = await evaluate_sentiment_escalation(
        conversation_id, msg.external_id, msg.customer_name, msg.text, sentiment_history
    )
    escalated = escalation["should_escalate"]

    if low_confidence and not escalated:
        # RAG had nothing confident to say — hand off instead of guessing.
        escalated = True
        await mark_escalated(conversation_id, "RAG confidence below similarity threshold")
        await send_slack_alert(
            conversation_id=conversation_id,
            chat_id=msg.external_id,
            customer_name=msg.customer_name,
            last_message=msg.text,
            reason="RAG confidence below similarity threshold — no relevant knowledge found",
        )

    await save_message(
        conversation_id=conversation_id,
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
        conversation_id=conversation_id,
    )
