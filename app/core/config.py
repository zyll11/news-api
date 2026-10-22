"""Application settings loaded from environment variables (and an optional .env file)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "News API"
    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://news:news@localhost:5432/news"
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: SecretStr
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_ttl_minutes: int = Field(default=15, ge=1)
    refresh_token_ttl_days: int = Field(default=30, ge=1)
    max_sessions_per_user: int = Field(default=5, ge=1)

    # Brute-force protection: failed logins per (IP, email) within the window
    login_rate_limit: int = Field(default=5, ge=1)
    login_rate_window_seconds: int = Field(default=300, ge=1)

    # Caching
    news_cache_ttl_seconds: int = Field(default=300, ge=1)

    # GitHub OAuth (disabled when client id/secret are empty)
    github_client_id: str | None = None
    github_client_secret: SecretStr | None = None
    public_base_url: str = "http://localhost:8000"

    cors_origins: list[str] = Field(default_factory=list)

    @field_validator("jwt_secret")
    @classmethod
    def _secret_is_strong(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")
        return value

    @property
    def github_oauth_enabled(self) -> bool:
        return bool(
            self.github_client_id
            and self.github_client_secret
            and self.github_client_secret.get_secret_value()
        )

    @property
    def github_redirect_uri(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/api/v1/auth/github/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
