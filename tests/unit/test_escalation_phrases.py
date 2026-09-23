import pytest

from escalation.phrases import is_explicit_human_request


@pytest.mark.parametrize("text", [
    "I want to talk to a human",
    "Can you connect me to a live agent?",
    "Let me SPEAK TO AGENT please",
    "transfer me to a support representative",
])
def test_explicit_requests_are_detected(text):
    assert is_explicit_human_request(text) is True


@pytest.mark.parametrize("text", [
    "What's your refund policy?",
    "hello",
    "thanks, that helped",
    "",
])
def test_normal_messages_are_not_flagged(text):
    assert is_explicit_human_request(text) is False
