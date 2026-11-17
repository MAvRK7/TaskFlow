"""Application configuration from environment variables.

Environment variables are loaded from a ``.env`` file when this module is
imported (which happens at FastAPI startup). ``.env`` is gitignored and must
never be committed; ``.env.example`` provides the template.
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Runtime configuration loaded from environment variables.

    All credentials and connection strings are sourced from the environment.
    Provide values via a ``.env`` file (see ``.env.example``) or your shell.
    Never hard-check secrets into this file.
    """

    def __init__(self) -> None:
        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg2://postgres:postgres@localhost:5432/taskflow",
        )
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.app_env = os.getenv("APP_ENV", "development")
        self.log_level = os.getenv("LOG_LEVEL", "info")


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()


__all__ = ["Settings", "get_settings"]
