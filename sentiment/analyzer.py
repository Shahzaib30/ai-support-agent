import json
import os

from dotenv import load_dotenv
from loguru import logger
from openai import AsyncOpenAI

load_dotenv()

client = AsyncOpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
)

MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


async def analyze(text: str) -> dict:
    prompt = f"""You are a sentiment analyzer for customer support.

Message: "{text}"

Rules:
- negative: customer is CLEARLY angry, frustrated, or complaining
- neutral: casual phrases, short responses, confusion, greetings
- positive: happy, satisfied, thankful

Examples:
"oh no" → neutral
"uh no" → neutral
"wtf" → neutral (not clearly angry enough)
"this is terrible I want a refund NOW" → negative
"your service is awful" → negative
"ok great" → positive
"how can you help me" → neutral

Reply ONLY with JSON:
{{"label": "positive" | "neutral" | "negative", "score": float -1.0 to 1.0}}"""
    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,
            temperature=0,
        )

        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)

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
