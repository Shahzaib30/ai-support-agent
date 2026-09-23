from connectors.base import IncomingMessage


def to_incoming_message(body: dict) -> IncomingMessage | None:
    """
    Normalizes a WhatsApp Cloud API webhook payload into an IncomingMessage.
    Returns None for non-message webhook events (delivery/read receipts etc).

    Meta's Cloud API webhook is at-least-once delivery, so the message's own
    `id` is carried through as metadata.event_id for idempotency.
    """
    entry = body["entry"][0]
    changes = entry["changes"][0]
    value = changes["value"]

    if "messages" not in value:
        return None

    msg = value["messages"][0]
    from_number = msg["from"]
    message_text = msg["text"]["body"]
    customer_name = value.get("contacts", [{}])[0].get("profile", {}).get("name", None)

    return IncomingMessage(
        channel="whatsapp",
        customer_id=from_number,
        message=message_text,
        customer_name=customer_name,
        metadata={"event_id": msg["id"]} if msg.get("id") else {},
    )
