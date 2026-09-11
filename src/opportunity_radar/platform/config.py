from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    ollama_base_url: str = "http://localhost:11434"
    ollama_model_analysis: str = "llama3.2:3b"
    ollama_health_timeout_seconds: float = 1.0
    frontend_origin: str = "http://localhost:3000"
    collection_timezone: str = "UTC"


@lru_cache
def get_settings() -> Settings:
    return Settings()
