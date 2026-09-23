import json
import os
import re
from datetime import date, time
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]

META_ATTRIBUTION_WINDOW_VALUES = frozenset(
    {"1d_click", "7d_click", "28d_click", "1d_view", "7d_view", "28d_view", "1d_ev"}
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    app_env: Literal["development", "test", "production"] = "development"
    admin_api_token: SecretStr = SecretStr("")
    database_url: SecretStr = SecretStr("")
    cors_origins: list[str] = ["http://localhost:3000"]
    # Optional read-only Meta Ads settings; the app runs without them.
    meta_ad_account_id: str = ""
    meta_access_token: SecretStr = SecretStr("")
    meta_graph_api_version: str = ""
    meta_sync_start_date: date | None = None
    meta_sync_lookback_days: int = Field(default=7, ge=1, le=90)
    meta_attribution_windows: Annotated[list[str], NoDecode] = ["7d_click", "1d_view"]
    meta_action_report_time: Literal["impression", "conversion", "mixed"] = "conversion"
    # Daily scheduled sync time in the ad account's timezone (HH:MM).
    meta_sync_time: time = time(6, 0)

    @field_validator(
        "meta_sync_start_date", "meta_sync_lookback_days", "meta_action_report_time",
        "meta_sync_time", mode="before",
    )
    @classmethod
    def blank_meta_values_use_defaults(cls, value, info):
        if isinstance(value, str) and not value.strip():
            return cls.model_fields[info.field_name].get_default(call_default_factory=True)
        return value

    @field_validator("meta_ad_account_id")
    @classmethod
    def validate_meta_account(cls, value: str) -> str:
        value = value.strip().removeprefix("act_")
        if value and not value.isdigit():
            raise ValueError("META_AD_ACCOUNT_ID must be numeric, optionally prefixed act_")
        return value

    @field_validator("meta_graph_api_version")
    @classmethod
    def validate_meta_version(cls, value: str) -> str:
        value = value.strip()
        if value and not re.fullmatch(r"v\d{1,3}\.\d{1,2}", value):
            raise ValueError("META_GRAPH_API_VERSION must look like v23.0")
        return value

    @field_validator("meta_attribution_windows", mode="before")
    @classmethod
    def parse_meta_windows(cls, value):
        if isinstance(value, str) and not value.strip():
            return ["7d_click", "1d_view"]
        if isinstance(value, str) and value.strip().startswith("["):
            try:
                return json.loads(value)
            except ValueError:
                # Shells and env loaders often strip the inner quotes: [7d_click,1d_view]
                value = value.strip().strip("[]")
        if isinstance(value, str):
            return [item.strip().strip("\"'") for item in value.split(",") if item.strip()]
        return value

    @field_validator("meta_attribution_windows")
    @classmethod
    def validate_meta_windows(cls, value: list[str]) -> list[str]:
        unknown = set(value) - META_ATTRIBUTION_WINDOW_VALUES
        if unknown or not value:
            raise ValueError("META_ATTRIBUTION_WINDOWS contains an unsupported window")
        return sorted(set(value))

    @property
    def meta_configured(self) -> bool:
        return bool(
            self.meta_ad_account_id
            and self.meta_access_token.get_secret_value()
            and self.meta_graph_api_version
        )

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
