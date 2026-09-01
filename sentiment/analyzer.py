import os
from loguru import logger
from dotenv import load_dotenv
from transformers import pipeline

load_dotenv()

logger.info("Sentiment thresholds initialized.")

NEGATIVE_THRESHOLD = float(os.getenv("SENTIMENT_NEGATIVE_THRESHOLD",-0.5))    
ESCALATION_COUNT = float(os.getenv("SENTIMENT_ESCALATION_COUNT",3))


_sentiment_model = None

def get_model():
    global _sentiment_model
    if _sentiment_model is None:
        logger.info("Loading sentiment analysis model...")
        _sentiment_model = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english", truncation=True, max_length=512)
        logger.success("Sentiment model loaded")
    return _sentiment_model

def analyze(text: str) -> dict:
    """
    Analyze sentiment of one message.
    Returns:
    {
        label : "positive" | "neutral" | "negative"
        score : float between -1.0 and 1.0
        }
        
    Now Score works:
        1.0 = very postive
        0.0 = neutral
       -1.0 = very negative
       """

    model = get_model()
    result = model(text)[0]

    raw_label = result["label"]
    raw_score = result["score"]

    if raw_label == "POSITIVE":
        score = raw_score
        label = "positive"

    else:
        score = -raw_score
        label = "negative"

    if -0.5 < score < 0.5:
        label = "neutral"

    logger.debug(f"Sentiment : {label} ({score:.2f}) - {text[:50]}")

    return {
        "label" : label,
        "score" : round(score, 4)
    }

# track conversation sentiment 

def check_escalation(sentiment_history: list[dict]) -> dict:
    """
    Check if the conversation need escalation.
    Rules:
     -> 3 consecutive negative messages with score < NEGATIVE_THRESHOLD
     -> resets if customer sends postive/ neutral message

     sentiment_history : list of past sentiment results:
     [
        {"label": "negative", "score": -0.8},
        {"label": "negative", "score": -0.7},
        {"label": "negative", "score": -0.9},
     ]

     Returns:
        {
            "should_escalate": True | False,
            consecutive_negative : int
            reason : str
        }
    """

    if not sentiment_history:
        return {
            "should_escalate": False,
            "consecutive_negative": 0,
            "reason": "No sentiment history"
        }

    consecutive_negative = 0
    for item in sentiment_history:
        if item["label"] == "negative":
            consecutive_negative += 1
        else:
            break

    should_escalate = consecutive_negative >=ESCALATION_COUNT

    return {
        "should_escalates" : should_escalate,
        "consecutive_negative" : consecutive_negative,
        "reason" : f"{consecutive_negative} consecutive negative messages"
    }


# step 3 -> full pipeline

def run_sentiment_pipeline(message: str, sentiment_history: list[dict]) -> dict:
    """Full Pipeline: 
        1. Analyze current Message
        2. Add to history
        3. check if escalation needed
        4. return everything.
        
        Returns:
        {
            "current_sentiment": {"label": "negative", "score": -0.8},
            "sentiment_history": [...],
            "escalation_check": {"should_escalate": True, "consecutive_negative": 3, "reason": "..."}
        }
        """
    current_sentiment = analyze(message)
    sentiment_history.append(current_sentiment)
    escalation_check = check_escalation(sentiment_history)

    if escalation_check["should_escalates"]:
        logger.warning(f"Escalation needed: {escalation_check['reason']}")

    return {
        "current_sentiment": current_sentiment,
        "sentiment_history": sentiment_history,
        "escalation_check": escalation_check
    }