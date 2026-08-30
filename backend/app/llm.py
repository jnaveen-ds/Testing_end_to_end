"""LLM provider abstraction.

- FakeLLMProvider: deterministic, free, offline. Default everywhere (dev/CI).
- AzureOpenAIProvider: real calls; only used when LLM_PROVIDER=azure.

Both return the same AnalysisResult so the rest of the app never cares
which one is active — the same pattern you'd use to swap any external
dependency in a larger system.
"""

import json
import time
from dataclasses import dataclass
from typing import Protocol

from app.config import Settings, get_settings

STOPWORDS = {
    "the", "and", "a", "an", "to", "of", "is", "it", "in", "this", "that",
    "was", "for", "with", "but", "have", "has", "not", "are", "were", "you",
    "your", "they", "their", "i", "we", "our", "my", "on", "at", "be", "as",
    "so", "too", "very", "just", "about", "would", "could", "should", "get",
}
POSITIVE_WORDS = {"good", "great", "excellent", "love", "amazing", "fast", "easy", "helpful", "perfect", "fantastic"}
NEGATIVE_WORDS = {"bad", "slow", "terrible", "hate", "broken", "buggy", "awful", "worst", "poor", "crash", "expensive"}


@dataclass
class AnalysisResult:
    summary: str
    sentiment: str
    themes: list[str]
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


class LLMProvider(Protocol):
    def analyze(self, text: str) -> AnalysisResult: ...


class FakeLLMProvider:
    """Deterministic offline "LLM". Free, instant, and stable for tests/CI."""

    def analyze(self, text: str) -> AnalysisResult:
        started = time.perf_counter()

        lowered = text.lower()
        pos = sum(1 for w in POSITIVE_WORDS if w in lowered)
        neg = sum(1 for w in NEGATIVE_WORDS if w in lowered)
        if pos > neg:
            sentiment = "positive"
        elif neg > pos:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        words = [w.strip(".,!?;:()\"'") for w in lowered.split()]
        counts: dict[str, int] = {}
        for w in words:
            if len(w) > 4 and w not in STOPWORDS and w not in POSITIVE_WORDS and w not in NEGATIVE_WORDS:
                counts[w] = counts.get(w, 0) + 1
        themes = [w for w, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:3]]

        summary = text.strip().replace("\n", " ")[:200]
        if len(text.strip()) > 200:
            summary += "..."

        prompt_tokens = max(1, len(text) // 4)
        completion_tokens = max(1, (len(summary) + len(sentiment)) // 4)
        latency_ms = int((time.perf_counter() - started) * 1000)

        return AnalysisResult(
            summary=summary,
            sentiment=sentiment,
            themes=themes,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )


class AzureOpenAIProvider:
    """Real Azure OpenAI calls. Requires LLM_PROVIDER=azure plus endpoint/key env vars."""

    def __init__(self, settings: Settings):
        if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
            raise RuntimeError(
                "Azure OpenAI is not configured: set AZURE_OPENAI_ENDPOINT and "
                "AZURE_OPENAI_API_KEY (never commit them; use .env or Key Vault)."
            )
        from openai import AzureOpenAI  # imported lazily so CI/dev never needs it

        self._client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        self._deployment = settings.azure_openai_deployment

    def analyze(self, text: str) -> AnalysisResult:
        started = time.perf_counter()
        response = self._client.chat.completions.create(
            model=self._deployment,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Analyze user feedback. Reply with JSON only: "
                        '{"summary": str, "sentiment": "positive"|"neutral"|"negative", '
                        '"themes": [up to 3 short keywords]}'
                    ),
                },
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
        )
        content = json.loads(response.choices[0].message.content or "{}")
        return AnalysisResult(
            summary=str(content.get("summary", ""))[:500],
            sentiment=str(content.get("sentiment", "neutral")),
            themes=[str(t) for t in content.get("themes", [])][:3],
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


def get_provider(settings: Settings | None = None) -> LLMProvider:
    s = settings or get_settings()
    return AzureOpenAIProvider(s) if s.llm_provider == "azure" else FakeLLMProvider()
