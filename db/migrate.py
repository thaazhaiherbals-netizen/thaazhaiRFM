"""Explicit, transactional migration runner. Never invoked on application startup."""

import argparse
import hashlib
from pathlib import Path

from sqlalchemy import text

from apps.api.db import get_engine

ROOT = Path(__file__).parent


def run(seed: bool = False) -> None:
    with get_engine().begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(748192031)"))
        connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(name TEXT PRIMARY KEY, checksum TEXT NOT NULL, "
            "applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
        )
        files = sorted((ROOT / "migrations").glob("*.sql"))
        if seed:
            files += sorted((ROOT / "seeds").glob("*.sql"))
        for path in files:
            name = f"{path.parent.name}/{path.name}"
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            existing = connection.execute(
                text("SELECT checksum FROM schema_migrations WHERE name = :name"),
                {"name": name},
            ).scalar_one_or_none()
            if existing:
                if existing != checksum:
                    raise RuntimeError(f"Applied SQL changed: {name}; add a new migration instead")
                continue
            # Execute scripts without DBAPI bind parameters (SQL may contain %).
            with connection.connection.driver_connection.cursor() as cursor:
                cursor.execute(sql)
            connection.execute(
                text("INSERT INTO schema_migrations (name, checksum) VALUES (:name, :checksum)"),
                {"name": name, "checksum": checksum},
            )
            print(f"Applied {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", action="store_true", help="Also apply confirmed master seeds")
    args = parser.parse_args()
    run(seed=args.seed)
