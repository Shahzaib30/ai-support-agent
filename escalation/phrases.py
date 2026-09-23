HUMAN_REQUEST_PHRASES = [
    "talk to agent",     "talk to human",    "talk to a human",
    "real person",       "human agent",      "connect me to",
    "transfer me",       "speak to someone", "i want a human",
    "need a human",      "get me a human",   "want to speak",
    "want to talk to",   "actual person",    "live agent",
    "speak to a person", "speak to agent",   "to an agent",
    "to a human",        "to a human agent", "to a real person",
    "to a live agent",   "to a support agent", "to a support person",
    "to a support representative", "to a customer service agent",
    "to a customer service representative", "to a customer support agent",
    "to a customer support representative", "to a customer care agent",
    "to a customer care representative", "to a technical support agent",
    "to a technical support representative", "to a help desk agent",
    "to a help desk representative", "to a service desk agent",
    "to a service desk representative", "to a support specialist",
    "to a customer service specialist", "to a customer support specialist",
    "to a customer care specialist", "to a technical support specialist",
    "to a help desk specialist", "to a service desk specialist",
    "to a support representative", "to a customer service representative",
    "to a customer support representative", "to a customer care representative",
    "to a technical support representative", "to a help desk representative",
    "to a service desk representative", "to a support agent",
    "to a customer service agent", "to a customer support agent",
    "to a customer care agent", "to a technical support agent",
    "to a help desk agent", "to a service desk agent", "to a support specialist",
    "to a customer service specialist", "to a customer support specialist",
    "to a customer care specialist", "to a technical support specialist",
    "to a help desk specialist", "to a service desk specialist",
    "to a support representative", "to a customer service representative",
    "to a customer support representative", "to a customer care representative",
    "to a technical support representative", "to a help desk representative",
    "to a service desk representative",
]


def is_explicit_human_request(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in HUMAN_REQUEST_PHRASES)
