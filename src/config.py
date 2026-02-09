"""Configuration management using pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Required (but optional for basic server startup)
    anthropic_api_key: str | None = None

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/agent_center.db"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    cors_origins: list[str] = ["*"]

    # Agent defaults
    default_model: str = "claude-sonnet-4-5"
    default_permission_mode: str = "default"

    # Security (Phase 2)
    api_key: str | None = None

    # Remote Access
    tailscale_hostname: str | None = None

    @property
    def database_path(self) -> Path:
        """Extract the database file path from the URL."""
        # Handle sqlite+aiosqlite:///./data/agent_center.db format
        url = self.database_url
        if url.startswith("sqlite"):
            # Remove the scheme prefix
            path_part = url.split("///")[-1]
            return Path(path_part)
        return Path("data/agent_center.db")

    def require_api_key(self) -> str:
        """Get API key, raising error if not configured."""
        if not self.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required. Set it in your .env file."
            )
        return self.anthropic_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear the settings cache. Use only in tests.

    This allows tests to reload settings with different
    environment variables.
    """
    get_settings.cache_clear()
