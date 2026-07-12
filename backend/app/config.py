from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API keys
    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")
    groq_api_key: str = Field(..., alias="GROQ_API_KEY")

    # Per-agent model IDs (can be overridden via env vars)
    # gemini-2.0-flash-lite was discontinued by Google (404 NOT_FOUND) — confirmed
    # working replacement is gemini-2.5-flash-lite (used throughout the BIRD eval).
    schema_linker_model: str = Field("openai/gpt-oss-20b", alias="SCHEMA_LINKER_MODEL")
    query_planner_model: str = Field("gemini-2.5-flash-lite", alias="QUERY_PLANNER_MODEL")
    sql_generator_model: str = Field("gemini-2.5-flash-lite", alias="SQL_GENERATOR_MODEL")
    explainer_model: str = Field("gemini-2.5-flash-lite", alias="EXPLAINER_MODEL")

    # Session management
    session_ttl_minutes: int = Field(30, alias="SESSION_TTL_MINUTES")

    # Observability (Phase 5 — optional for now)
    langfuse_public_key: str = Field("", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field("", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field("https://cloud.langfuse.com", alias="LANGFUSE_HOST")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
