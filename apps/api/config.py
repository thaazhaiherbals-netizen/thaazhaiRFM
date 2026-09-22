import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    app_env: Literal["development", "test", "production"] = "development"
    admin_api_token: SecretStr = SecretStr("")
    database_url: SecretStr = SecretStr("")
    cors_origins: list[str] = ["http://localhost:3000"]

    @model_validator(mode="after")
    def validate_database_target(self) -> "Settings":
        value = self.database_url.get_secret_value()
        if not value:
            if self.app_env == "production":
                raise ValueError("Production requires DATABASE_URL")
            return self
        try:
            url = make_url(value)
        except Exception:
            raise ValueError("DATABASE_URL must be a valid PostgreSQL URL") from None
        if url.get_backend_name() not in ("postgres", "postgresql"):
            raise ValueError("DATABASE_URL must use PostgreSQL")
        if self.app_env != "production":
            if url.host not in ("localhost", "127.0.0.1", "::1", "postgres"):
                raise ValueError(
                    "Development/test must use local PostgreSQL, not a remote database"
                )
            if any(key in url.query for key in ("host", "hostaddr", "service")):
                raise ValueError("Local connections cannot override the database host")
        return self


@lru_cache
def get_settings() -> Settings:
    # Select before reading any file: a file cannot switch us into production.
    selected = os.environ.get("APP_ENV", "development")
    files = {"development": ".env.local", "production": ".env.production", "test": None}
    if selected not in files:
        raise ValueError("APP_ENV must be development, test, or production")
    filename = files[selected]
    return Settings(
        app_env=selected,
        _env_file=PROJECT_ROOT / filename if filename else None,
    )
