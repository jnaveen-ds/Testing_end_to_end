"""Dedicated App 1 FastAPI entry point for an independent Container App."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.chat import router
from app.config import get_settings


settings = get_settings()
app = FastAPI(title="Real-time Chat API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "provider": settings.llm_provider}


@app.get("/ready")
def ready() -> dict:
    # App 1 degrades cache failures to a miss, so readiness depends on valid app config,
    # not on Redis being reachable at this exact moment.
    return {
        "status": "ready",
        "provider": settings.llm_provider,
        "cache_backend": settings.chat_cache_backend,
    }
