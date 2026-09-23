import os

from dotenv import load_dotenv

load_dotenv()

ESCALATION_COUNT = float(os.getenv("SENTIMENT_ESCALATION_COUNT", 3))


def check_consecutive_negatives(sentiment_history: list[dict]) -> dict:
    """
    Count consecutive negative messages from the end.
    If ESCALATION_COUNT or more → escalate.

    sentiment_history = [
      {"label": "negative", "score": -0.8},
      {"label": "negative", "score": -0.7},
      {"label": "negative", "score": -0.9},
    ]
    """
    if not sentiment_history:
        return {
            "should_escalate": False,
            "consecutive_negatives": 0,
            "reason": "No history yet",
        }

    consecutive = 0
    for sentiment in reversed(sentiment_history):
        if sentiment["label"] == "negative":
            consecutive += 1
        else:
            break

    should_escalate = consecutive >= ESCALATION_COUNT

    return {
        "should_escalate": should_escalate,
        "consecutive_negatives": consecutive,
        "reason": (
            f"{consecutive} consecutive negative messages"
            if should_escalate
            else "Within normal range"
        ),
    }
