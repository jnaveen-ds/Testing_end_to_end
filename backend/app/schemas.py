"""Pydantic request/response schemas."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AnalysisCreate(BaseModel):
    text: str = Field(min_length=1, max_length=20000, description="Feedback text to analyze")


class JobOut(BaseModel):
    id: str
    status: str
    input_text: str
    summary: str | None = None
    sentiment: str | None = None
    themes: list[str] | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int | None = None
    error: str | None = None

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    prompt: str = Field(
        min_length=1,
        max_length=2000,
        description="Question for the synchronous learning assistant",
    )

    @field_validator("prompt")
    @classmethod
    def prompt_must_have_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("prompt must contain text")
        return cleaned


class ChatResponse(BaseModel):
    answer: str
    cache_status: Literal["HIT", "MISS"]
    prompt_tokens: int
    completion_tokens: int
    model_latency_ms: int
    total_latency_ms: int
    correlation_id: str
