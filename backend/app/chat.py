"""App 1 synchronous chat route and cache-aside service."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from functools import lru_cache

from fastapi import APIRouter, Depends

from app.chat_cache import CachedChat, ChatCache, MemoryChatCache, RedisChatCache
from app.config import Settings, get_settings
from app.llm import LLMProvider, get_provider
from app.schemas import ChatRequest, ChatResponse


router = APIRouter(tags=["chat"])


def cache_key(prompt: str, settings: Settings) -> str:
    """Scope reusable output to every input that can change or authorize the answer."""
    normalized_prompt = " ".join(prompt.split())
    model = (
        settings.azure_openai_deployment
        if settings.llm_provider == "azure"
        else "fake-v1"
    )
    material = {
        "tenant_scope": settings.chat_tenant_scope,
        "prompt": normalized_prompt,
        "provider": settings.llm_provider,
        "model": model,
        "prompt_version": settings.chat_prompt_version,
        "temperature": 0,
    }
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"chat:{digest}"


class ChatService:
    def __init__(self, settings: Settings, provider: LLMProvider, cache: ChatCache):
        self._settings = settings
        self._provider = provider
        self._cache = cache

    def respond(self, prompt: str, correlation_id: str) -> ChatResponse:
        started = time.perf_counter()
        key = cache_key(prompt, self._settings)
        cached = self._cache.get(key)
        if cached is not None:
            return self._hit(cached, correlation_id, started)

        with self._cache.lock(key):
            # A concurrent request may have populated the key while this request waited.
            cached = self._cache.get(key)
            if cached is not None:
                return self._hit(cached, correlation_id, started)

            result = self._provider.chat(prompt)
            self._cache.set(
                key,
                CachedChat(answer=result.answer),
                self._settings.chat_cache_ttl_seconds,
            )
            return ChatResponse(
                answer=result.answer,
                cache_status="MISS",
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                model_latency_ms=result.latency_ms,
                total_latency_ms=int((time.perf_counter() - started) * 1000),
                correlation_id=correlation_id,
            )

    @staticmethod
    def _hit(
        cached: CachedChat,
        correlation_id: str,
        started: float,
    ) -> ChatResponse:
        return ChatResponse(
            answer=cached.answer,
            cache_status="HIT",
            prompt_tokens=0,
            completion_tokens=0,
            model_latency_ms=0,
            total_latency_ms=int((time.perf_counter() - started) * 1000),
            correlation_id=correlation_id,
        )


@lru_cache
def get_chat_service() -> ChatService:
    settings = get_settings()
    if settings.chat_cache_backend == "memory":
        cache: ChatCache = MemoryChatCache()
    elif settings.chat_cache_backend == "redis":
        cache = RedisChatCache(settings.redis_url)
    else:
        raise RuntimeError(
            "CHAT_CACHE_BACKEND must be 'memory' or 'redis', got "
            f"{settings.chat_cache_backend!r}"
        )
    return ChatService(settings, get_provider(settings), cache)


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    return service.respond(payload.prompt, uuid.uuid4().hex)
