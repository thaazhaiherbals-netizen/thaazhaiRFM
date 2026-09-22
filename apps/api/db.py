from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url

from apps.api.config import get_settings


@lru_cache
def get_engine() -> Engine:
    value = get_settings().database_url.get_secret_value()
    if not value:
        raise RuntimeError("DATABASE_URL is not configured")
    url = make_url(value)
    if url.get_backend_name() not in ("postgres", "postgresql"):
        raise ValueError("DATABASE_URL must use PostgreSQL")
    url = url.set(drivername="postgresql+psycopg")
    if get_settings().app_env == "production":
        url = url.update_query_dict({"sslmode": "require"})
    return create_engine(
        url, pool_pre_ping=True, pool_size=5, max_overflow=5,
        connect_args={"connect_timeout": 5}, hide_parameters=True,
    )
