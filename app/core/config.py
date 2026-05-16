from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_key: str = ""
    jwt_secret: str = ""
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "sqlite+aiosqlite:///./data/review.db"  # V1 compat
    postgres_url: str = "postgresql+asyncpg://review:review@postgres:5432/reviewdb"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    telegram_bot_token: str = ""
    telegram_allowed_chat_ids: str = ""  # Comma-separated chat IDs, e.g. "123456,789012"
    review_timeout_minutes: int = 1440  # 24 hours default for APPROVING state timeout

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
