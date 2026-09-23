from dataclasses import dataclass


@dataclass
class InboundMessage:
    """Channel-agnostic representation of a customer message.

    Every connector (WhatsApp, Telegram, Discord, Web) must normalize its
    platform-specific payload into this shape before handing it to the
    core agent pipeline, so agent logic never has to know which channel
    a message came from.
    """

    channel: str
    external_id: str
    text: str
    customer_name: str | None = None


@dataclass
class AgentReply:
    """Result of running an InboundMessage through the core agent pipeline."""

    answer: str
    escalated: bool
    cache_hit: bool
    sentiment_label: str
    sentiment_score: float
    conversation_id: str
