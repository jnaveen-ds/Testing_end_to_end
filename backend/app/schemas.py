"""Pydantic request/response schemas."""

from pydantic import BaseModel, Field


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
