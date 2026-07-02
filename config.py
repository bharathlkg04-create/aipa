from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent / ".env"


class Settings(BaseSettings):
    SUPABASE_DB_URL: str
    FERNET_KEY: str

    BASE_URL: str = ""

    # Platform-level embedding credentials for skill retrieval.
    # When EMBEDDING_API_KEY is empty, skill selection falls back to
    # pinned + most recently enabled skills (no vector search).
    EMBEDDING_MODEL: str = "openai/text-embedding-3-small"
    EMBEDDING_API_KEY: str = ""
    MAX_SKILLS_IN_PROMPT: int = 5

    ENVIRONMENT: str = "production"
    LOG_LEVEL: str = "INFO"
    PORT: int = 8000

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
