"""Application configuration.

Everything comes from environment variables (or a local .env file).
Defaults are chosen so the app runs 100% locally with zero cloud cost:

- LLM_PROVIDER=fake   -> deterministic offline "LLM", no tokens billed
- LLM_PROVIDER=azure  -> real Azure OpenAI calls (only for controlled tests)
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Infrastructure
    database_url: str = "sqlite:///./local.db"
    redis_url: str = "redis://localhost:6379/0"

    # LLM provider: "fake" (default, free) or "azure"
    llm_provider: str = "fake"

    # Azure OpenAI (only used when llm_provider == "azure").
    # Never commit real values: put them in .env / Key Vault later.
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = "gpt-5.4-mini"
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_auth: str = "api_key"
    azure_managed_identity_client_id: str = ""

    # App 1 synchronous chat. Tests use the in-memory cache; Docker Compose uses Redis.
    chat_cache_backend: str = "memory"
    chat_cache_ttl_seconds: int = 900
    chat_prompt_version: str = "v1"
    chat_tenant_scope: str = "public-learning-demo"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
