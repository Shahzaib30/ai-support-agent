from connectors.base import InboundMessage


def to_inbound_message(body: dict) -> InboundMessage | None:
    """
    Normalizes a WhatsApp Cloud API webhook payload into an InboundMessage.
    Returns None for non-message webhook events (delivery/read receipts etc).
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

    return InboundMessage(
        channel="whatsapp",
        external_id=from_number,
        text=message_text,
        customer_name=customer_name,
    )
