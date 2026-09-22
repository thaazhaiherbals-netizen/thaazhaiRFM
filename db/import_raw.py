"""Read Supabase raw ingestion into local PostgreSQL; never update the source."""
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import dotenv_values

from apps.api.config import get_settings
from apps.api.db import get_engine

COLUMNS = (
    "id", "source_system", "source_record_id", "raw_payload", "status", "retry_count",
    "error_message", "ingested_at", "processing_started_at", "processed_at",
    "created_at", "updated_at",
)
SOURCE = "https://cfqsjiaqayvkyfxykjwa.supabase.co"
TIMES = set(COLUMNS[7:])


def download(client: httpx.Client) -> list[dict]:
    rows = []
    last_id = None
    expected = None
    while True:
        params = {"select": ",".join(COLUMNS), "order": "id.asc", "limit": "500"}
        if last_id:
            params["id"] = f"gt.{last_id}"
        response = client.get("/rest/v1/raw_order_ingestion", params=params)
        if response.status_code not in (200, 206):
            raise RuntimeError(f"Supabase read failed (HTTP {response.status_code})")
        if expected is None:
            total = response.headers.get("content-range", "").split("/")[-1]
            if not total.isdigit():
                raise RuntimeError("Source did not return an exact record count")
            expected = int(total)
        page = response.json()
        if not isinstance(page, list):
            raise RuntimeError("Unexpected source response")
        if not page:
            break
        for row in page:
            if set(row) != set(COLUMNS):
                raise RuntimeError("Source schema differs from expected raw ingestion columns")
        if last_id and page[-1]["id"] <= last_id:
            raise RuntimeError("Source pagination did not advance")
        rows.extend(page)
        last_id = page[-1]["id"]
    if len(rows) != expected or len({r["id"] for r in rows}) != expected:
        raise RuntimeError("Source count changed or duplicate IDs found; rerun the copy")
    return rows


def comparable(row: dict) -> dict:
    result = dict(row)
    result["id"] = str(result["id"])
    for key in TIMES:
        value = result[key]
        if isinstance(value, str):
            result[key] = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result


def main() -> None:
    if get_settings().app_env != "development":
        raise RuntimeError("Import is allowed only in development")
    engine = get_engine()
    if engine.url.host != "postgres" or engine.url.database != "thaazhai_dev":
        raise RuntimeError("Destination must be the Docker local thaazhai_dev database")
    secrets = dotenv_values(Path("/run/supabase.env"))
    if str(secrets.get("SUPABASE_URL", "")).rstrip("/") != SOURCE:
        raise RuntimeError("SUPABASE_URL must match the supplied project base URL")
    key = secrets.get("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is missing")
    headers = {"apikey": key, "Prefer": "count=exact"}
    # Legacy service_role keys are JWTs; new secret keys use only apikey.
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    with httpx.Client(base_url=SOURCE, headers=headers, timeout=60) as client:
        rows = download(client)
        if rows != download(client):
            raise RuntimeError("Source changed during verification; rerun when ingestion is quiet")
    print(f"Source verified: {len(rows)} records; payloads and lifecycle fields preserved.")
    placeholders = ", ".join("%s::jsonb" if c == "raw_payload" else "%s" for c in COLUMNS)
    statement = (
        f"INSERT INTO raw_order_ingestion ({', '.join(COLUMNS)}) VALUES ({placeholders}) "
        "ON CONFLICT (id) DO NOTHING"
    )
    inserted = 0
    with engine.begin() as connection:
        with connection.connection.driver_connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(748192032)")
            for row in rows:
                values = [
                    json.dumps(row[c], ensure_ascii=False) if c == "raw_payload" else row[c]
                    for c in COLUMNS
                ]
                cursor.execute(statement, values)
                inserted += cursor.rowcount
                cursor.execute(
                    f"SELECT {', '.join(COLUMNS)} FROM raw_order_ingestion WHERE id = %s",
                    (row["id"],),
                )
                local = dict(zip(COLUMNS, cursor.fetchone(), strict=True))
                if comparable(local) != comparable(row):
                    raise RuntimeError(
                        "An existing local record differs from source; no records were committed"
                    )
            cursor.execute("SELECT count(*) FROM raw_order_ingestion")
            total = cursor.fetchone()[0]
    print(f"Committed: {inserted} new, {len(rows) - inserted} identical existing.")
    print(f"Local total: {total}. All {len(rows)} source records verified field by field.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Do not print database statements, customer payloads, or authentication details.
        if type(exc) is RuntimeError:
            print(str(exc), file=sys.stderr)
        else:
            print(f"Copy failed ({type(exc).__name__}); transaction rolled back.", file=sys.stderr)
        sys.exit(1)


