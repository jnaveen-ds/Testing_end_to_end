"""App 1 chat tests: synchronous API, TTL cache, key scope, and stampede lock."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.chat import ChatService, cache_key, get_chat_service
from app.chat_cache import CachedChat, MemoryChatCache
from app.config import Settings
from app.llm import ChatResult, FakeLLMProvider
from app.main import app


class CountingProvider:
    def __init__(self, delay_seconds: float = 0):
        self.calls = 0
        self._delay_seconds = delay_seconds
        self._guard = threading.Lock()

    def chat(self, prompt: str) -> ChatResult:
        with self._guard:
            self.calls += 1
        if self._delay_seconds:
            time.sleep(self._delay_seconds)
        return ChatResult(
            answer=f"answer:{prompt}",
            prompt_tokens=7,
            completion_tokens=3,
            latency_ms=5,
        )


def make_service(provider=None, cache=None, **settings_overrides) -> ChatService:
    settings = Settings(
        llm_provider="fake",
        chat_cache_backend="memory",
        **settings_overrides,
    )
    return ChatService(
        settings,
        provider or FakeLLMProvider(),
        cache or MemoryChatCache(),
    )


def test_chat_endpoint_reports_miss_then_hit_with_zero_hit_tokens(client):
    service = make_service()
    app.dependency_overrides[get_chat_service] = lambda: service
    try:
        first = client.post("/chat", json={"prompt": "Explain scale to zero"})
        second = client.post("/chat", json={"prompt": "Explain scale to zero"})
    finally:
        app.dependency_overrides.pop(get_chat_service, None)

    assert first.status_code == 200
    assert first.json()["cache_status"] == "MISS"
    assert first.json()["prompt_tokens"] > 0
    assert second.json()["cache_status"] == "HIT"
    assert second.json()["prompt_tokens"] == 0
    assert second.json()["completion_tokens"] == 0
    assert second.json()["answer"] == first.json()["answer"]
    assert second.json()["correlation_id"] != first.json()["correlation_id"]


def test_chat_rejects_blank_and_oversized_prompts(client):
    assert client.post("/chat", json={"prompt": "   "}).status_code == 422
    assert client.post("/chat", json={"prompt": "x" * 2001}).status_code == 422


def test_cache_key_changes_for_security_and_model_boundaries():
    base = Settings(llm_provider="fake", chat_tenant_scope="tenant-a")
    assert cache_key("same prompt", base) != cache_key(
        "same prompt",
        Settings(llm_provider="fake", chat_tenant_scope="tenant-b"),
    )
    assert cache_key("same prompt", base) != cache_key(
        "same prompt",
        Settings(
            llm_provider="fake",
            chat_tenant_scope="tenant-a",
            chat_prompt_version="v2",
        ),
    )
    assert cache_key("same prompt", base) == cache_key(" same   prompt ", base)


def test_memory_cache_expires_at_ttl_boundary():
    now = [100.0]
    cache = MemoryChatCache(clock=lambda: now[0])
    cache.set("key", CachedChat(answer="temporary"), ttl_seconds=15)

    assert cache.get("key") == CachedChat(answer="temporary")
    now[0] = 115.0
    assert cache.get("key") is None


def test_concurrent_identical_misses_call_provider_once():
    provider = CountingProvider(delay_seconds=0.03)
    service = make_service(provider=provider)

    with ThreadPoolExecutor(max_workers=12) as pool:
        responses = list(
            pool.map(
                lambda number: service.respond("same burst", f"request-{number}"),
                range(20),
            )
        )

    assert provider.calls == 1
    assert sum(response.cache_status == "MISS" for response in responses) == 1
    assert sum(response.cache_status == "HIT" for response in responses) == 19
