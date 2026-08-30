"""Unit tests for the fake LLM provider (no DB, no broker, no network)."""

from app.llm import FakeLLMProvider


def test_positive_sentiment():
    result = FakeLLMProvider().analyze("This product is great, I love how fast it is!")
    assert result.sentiment == "positive"


def test_negative_sentiment():
    result = FakeLLMProvider().analyze("Terrible experience. The app is slow and keeps crashing.")
    assert result.sentiment == "negative"


def test_neutral_sentiment():
    result = FakeLLMProvider().analyze("The package arrived on Tuesday near the front desk")
    assert result.sentiment == "neutral"


def test_themes_are_frequent_meaningful_words():
    result = FakeLLMProvider().analyze("Shipping was delayed. Shipping costs increased again. Shipping updates are unclear.")
    assert "shipping" in result.themes


def test_deterministic_usage_accounting():
    text = "same text"
    first = FakeLLMProvider().analyze(text)
    second = FakeLLMProvider().analyze(text)
    assert (first.prompt_tokens, first.completion_tokens) == (second.prompt_tokens, second.completion_tokens)
    assert first.prompt_tokens > 0
