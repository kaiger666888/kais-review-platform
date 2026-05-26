from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database (PostgreSQL + TimescaleDB)
    postgres_url: str = "postgresql+asyncpg://review:review@postgres:5432/reviewdb"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # MinIO (S3-compatible object storage)
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "review-platform"
    minio_secure: bool = False  # LAN, no TLS

    # Git (GitOps policy-as-code)
    git_repo_url: str = ""
    git_branch: str = "main"

    # Auth (inter-service auth removed; kept for web UI login)
    api_key: str = ""
    jwt_secret: str = "dev-no-auth"
    capability_token_secret: str = ""  # Phase 19 token issuance

    # General
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    # Review timeouts
    review_timeout_minutes: int = 1440  # 24h human review timeout
    ai_audit_timeout_minutes: int = 5  # 5min AI audit timeout

    # Retention (days)
    hot_retention_days: int = 30
    warm_retention_days: int = 365

    # Telegram (kept for backward compat)
    telegram_bot_token: str = ""
    telegram_allowed_chat_ids: str = ""  # Comma-separated chat IDs

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
