from escalation.sentiment_gate import check_consecutive_negatives


def test_empty_history_does_not_escalate():
    result = check_consecutive_negatives([])
    assert result["should_escalate"] is False
    assert result["consecutive_negatives"] == 0


def test_three_consecutive_negatives_escalates():
    history = [
        {"label": "negative", "score": -0.8},
        {"label": "negative", "score": -0.7},
        {"label": "negative", "score": -0.9},
    ]
    result = check_consecutive_negatives(history)
    assert result["should_escalate"] is True
    assert result["consecutive_negatives"] == 3


def test_two_consecutive_negatives_does_not_escalate():
    history = [
        {"label": "negative", "score": -0.8},
        {"label": "negative", "score": -0.7},
    ]
    result = check_consecutive_negatives(history)
    assert result["should_escalate"] is False
    assert result["consecutive_negatives"] == 2


def test_only_counts_the_trailing_negative_streak():
    history = [
        {"label": "negative", "score": -0.9},
        {"label": "negative", "score": -0.9},
        {"label": "negative", "score": -0.9},
        {"label": "positive", "score": 0.6},
        {"label": "negative", "score": -0.6},
    ]
    result = check_consecutive_negatives(history)
    assert result["should_escalate"] is False
    assert result["consecutive_negatives"] == 1
