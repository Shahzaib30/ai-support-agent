from dataclasses import dataclass, field


@dataclass
class IncomingMessage:
    """Channel-agnostic representation of a customer message.

    Every connector (WhatsApp, Telegram, Discord, Web) must normalize its
    platform-specific payload into this shape before handing it to the core
    agent pipeline, so agent logic never has to know which channel a message
    came from.

    `conversation_id` is unknown at normalization time (it's assigned by the
    database) — `core.agent.process_message` fills it in immediately after
    conversation lookup, so downstream escalation/Slack logic can pass this
    one object around instead of threading four loose parameters.

    `metadata` carries channel-specific extras that the core agent treats
    opaquely, e.g. an `event_id` used for webhook-retry idempotency, or a
    WhatsApp message id.
    """

    channel: str
    customer_id: str
    message: str
    customer_name: str | None = None
    conversation_id: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentReply:
    """Result of running an IncomingMessage through the core agent pipeline."""

    answer: str
    escalated: bool
    cache_hit: bool
    sentiment_label: str
    sentiment_score: float
    conversation_id: str
