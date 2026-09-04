import os
from loguru import logger
from dotenv import load_dotenv
from openai import OpenAI
load_dotenv()

logger.info("Sentiment thresholds initialized.")

NEGATIVE_THRESHOLD = float(os.getenv("SENTIMENT_NEGATIVE_THRESHOLD",-0.5))    
ESCALATION_COUNT = float(os.getenv("SENTIMENT_ESCALATION_COUNT",3))


client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
)

MODEL = os.getenv("DEEPSEEK_MODEL","deepseek-chat")

logger.info("Sentiment thresholds initialized.")



def analyze(text: str) -> dict:
    """
    Analyze sentiment of one message using DeepSeek.
 
    Returns:
    {
      label: "positive" | "neutral" | "negative"
      score: float between -1.0 and 1.0
    }
    """
    prompt = f"""Analyze the sentiment of this customer support message.
 
        Message: "{text}"
        
        Reply with ONLY a JSON object in this exact format, nothing else:
        {{"label": "positive" | "neutral" | "negative", "score": float between -1.0 and 1.0}}
        
        Rules:
        - score  1.0 = very happy
        - score  0.0 = neutral
        - score -1.0 = very angry
        - label must match score:
        positive → score > 0.5
        neutral  → score between -0.5 and 0.5
        negative → score < -0.5"""
 
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,
            temperature=0,
        )
 
        import json
        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)
 
        label = result.get("label", "neutral")
        score = float(result.get("score", 0.0))
 
        score = max(-1.0, min(1.0, score))
 
        if score > 0.5:
            label = "positive"
        elif score < -0.5:
            label = "negative"
        else:
            label = "neutral"
 
        logger.debug(f"Sentiment: {label} ({score:.2f}) — {text[:50]}")
        return {"label": label, "score": round(score, 4)}
 
    except Exception as e:
        logger.warning(f"Sentiment analysis failed: {e} — defaulting to neutral")
        return {"label": "neutral", "score": 0.0}
 
 

# track conversation sentiment 

def check_escalation(sentiment_history: list[dict]) -> dict:
    """
    Count consecutive negative messages from the end.
    If 3 or more → escalate.
 
    sentiment_history = [
      {"label": "negative", "score": -0.8},
      {"label": "negative", "score": -0.7},
      {"label": "negative", "score": -0.9},
    ]
    """
    if not sentiment_history:
        return {
            "should_escalate":       False,
            "consecutive_negatives": 0,
            "reason":                "No history yet",
        }
 
    consecutive = 0
    for sentiment in reversed(sentiment_history):
        if sentiment["label"] == "negative":
            consecutive += 1
        else:
            break
 
    should_escalate = consecutive >= ESCALATION_COUNT
 
    return {
        "should_escalate":       should_escalate,
        "consecutive_negatives": consecutive,
        "reason": (
            f"{consecutive} consecutive negative messages"
            if should_escalate
            else "Within normal range"
        ),
    }
 


# step 3 -> full pipeline

def run_sentiment_pipeline(
    message:           str,
    sentiment_history: list[dict],
) -> dict:
    """
    1. Analyze current message
    2. Add to history
    3. Check escalation
    4. Return result
    """
    current = analyze(message)
    sentiment_history.append(current)
    escalation = check_escalation(sentiment_history)
 
    if escalation["should_escalate"]:
        logger.warning(
            f"ESCALATION TRIGGERED — "
            f"{escalation['consecutive_negatives']} "
            f"consecutive negative messages"
        )
 
    return {
        "current":    current,
        "escalation": escalation,
    }