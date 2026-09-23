from loguru import logger


async def condense_query(question: str, chat_history: list[dict] | None, llm_client, model: str) -> str:
    """
    Rewrites a conversational follow-up ("what about the pro plan?") into a
    standalone search query using the preceding chat history, so the vector
    store isn't searched with ambiguous, context-dependent text.

    Returns the original question unchanged if there's no history to
    condense against, or if condensation fails for any reason.
    """
    if not chat_history:
        return question

    history_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in chat_history[-6:])

    try:
        response = await llm_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Rewrite the customer's latest message as a standalone search query "
                        "that captures its full meaning without needing the conversation history. "
                        "If it is already standalone, return it unchanged. "
                        "Reply with ONLY the rewritten query, no explanation, no quotes."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Conversation so far:\n{history_text}\n\nLatest message: {question}\n\nStandalone query:",
                },
            ],
            max_tokens=100,
            temperature=0,
        )
        condensed = response.choices[0].message.content.strip()
        if condensed:
            logger.debug(f"Condensed query: '{question[:60]}' -> '{condensed[:60]}'")
            return condensed
        return question
    except Exception as e:
        logger.warning(f"Query condensation failed, using original question: {e}")
        return question
