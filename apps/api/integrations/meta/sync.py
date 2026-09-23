"""Idempotent Meta Insights sync: append-only raw landing, then transactional normalization.

Flow for one run (docs/META_MARKETING_INTEGRATION.md "Sync and scheduling"):
1. Take a per-account session advisory lock so runs never overlap.
2. Record the run, then land every page as raw rows (committed per page).
3. Normalize this run's raw rows into dimensions + ad/day facts in ONE transaction,
   replacing facts for the same account, dates and attribution configuration so that
   restated or withdrawn rows are reflected. Raw history is never modified.
4. Store the account-level control spend beside the normalized total.
5. Mark SUCCEEDED only after every page and write succeeded.
"""

import hashlib
import json
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Connection, Engine, text

from apps.api.integrations.meta.client import INSIGHT_FIELDS, MetaApiError, MetaClient
from apps.api.integrations.meta.parser import MetaParseError, parse_insight_row, to_decimal

MAX_RANGE_DAYS = 93
LOCK_NAMESPACE = "meta_insights_sync:"


class SyncInProgress(RuntimeError):
    """Another sync for this ad account holds the lock."""


class InvalidSyncRange(ValueError):
    pass


def attribution_key(windows: list[str], report_time: str) -> str:
    return f"{','.join(sorted(windows))}|{report_time}"


def validate_range(
    date_from: date, date_to: date, today: date | None = None, max_days: int = MAX_RANGE_DAYS
) -> None:
    today = today or date.today()
    if date_from > date_to:
        raise InvalidSyncRange("date_from must be on or before date_to")
    if date_to > today:
        raise InvalidSyncRange("date_to cannot be in the future")
    if (date_to - date_from).days + 1 > max_days:
        raise InvalidSyncRange(f"A single run covers at most {max_days} days; use chunks")


def chunks(date_from: date, date_to: date, days: int) -> Iterator[tuple[date, date]]:
    start = date_from
    while start <= date_to:
        end = min(date_to, start + timedelta(days=days - 1))
        yield start, end
        start = end + timedelta(days=1)


def account_today(timezone_name: str | None, offset_hours: object = None) -> date:
    now = datetime.now(timezone.utc)
    if timezone_name:
        try:
            return now.astimezone(ZoneInfo(timezone_name)).date()
        except ZoneInfoNotFoundError:
            pass
    offset = to_decimal(offset_hours)
    if offset is not None:
        return (now + timedelta(hours=float(offset))).date()
    return now.date()


def recent_window(lookback_days: int, today: date) -> tuple[date, date]:
    """Re-fetch the lookback through yesterday because Meta restates recent conversions."""
    yesterday = today - timedelta(days=1)
    return yesterday - timedelta(days=lookback_days - 1), yesterday


def _lock_key(ad_account_id: str) -> str:
    return LOCK_NAMESPACE + ad_account_id


def run_sync(
    engine: Engine,
    client: MetaClient,
    *,
    ad_account_id: str,
    api_version: str,
    date_from: date,
    date_to: date,
    windows: list[str],
    report_time: str,
    trigger: str = "MANUAL",
    use_async: bool = False,
) -> UUID:
    validate_range(date_from, date_to)
    key = attribution_key(windows, report_time)
    with engine.connect() as lock_connection:
        locked = lock_connection.execute(
            text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"),
            {"key": _lock_key(ad_account_id)},
        ).scalar_one()
        lock_connection.commit()
        if not locked:
            raise SyncInProgress("A Meta sync is already running for this ad account")
        try:
            return _run_locked(
                engine, client, ad_account_id, api_version, date_from, date_to,
                windows, report_time, key, trigger, use_async,
            )
        finally:
            lock_connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                {"key": _lock_key(ad_account_id)},
            )
            lock_connection.commit()


def _run_locked(
    engine, client, ad_account_id, api_version, date_from, date_to,
    windows, report_time, key, trigger, use_async,
) -> UUID:
    with engine.begin() as connection:
        # We hold the lock, so any RUNNING row for this account is from a dead process.
        connection.execute(
            text("""
                UPDATE meta_insight_sync_runs
                SET status = 'FAILED', finished_at = NOW(),
                    error_summary = 'Interrupted before completion'
                WHERE ad_account_id = :account AND status = 'RUNNING'
            """),
            {"account": ad_account_id},
        )
        run_id = connection.execute(
            text("""
                INSERT INTO meta_insight_sync_runs (
                    ad_account_id, trigger, date_from, date_to, fields,
                    attribution_windows, action_report_time, attribution_key, api_version
                ) VALUES (
                    :account, :trigger, :date_from, :date_to, :fields,
                    :windows, :report_time, :key, :version
                ) RETURNING id
            """),
            {
                "account": ad_account_id, "trigger": trigger, "date_from": date_from,
                "date_to": date_to, "fields": list(INSIGHT_FIELDS), "windows": windows,
                "report_time": report_time, "key": key, "version": api_version,
            },
        ).scalar_one()
    try:
        account = client.get_account()
        _upsert_account(engine, ad_account_id, account)
        fetch = client.iter_async_insight_pages if use_async else client.iter_insight_pages
        for page in fetch(date_from, date_to, windows, report_time):
            _land_page(engine, run_id, page)
        control = to_decimal(client.account_spend(date_from, date_to, windows, report_time))
        with engine.begin() as connection:
            normalized = normalize_run(connection, run_id, account)
            connection.execute(
                text("""
                    UPDATE meta_insight_sync_runs
                    SET status = 'SUCCEEDED', finished_at = NOW(),
                        normalized_spend = :normalized, control_spend = :control,
                        attempt_count = :attempts, usage_headers = CAST(:usage AS JSONB)
                    WHERE id = :id
                """),
                {
                    "id": run_id, "normalized": normalized, "control": control,
                    "attempts": client.attempts, "usage": json.dumps(client.usage),
                },
            )
    except Exception as error:
        summary = str(error) if isinstance(error, (MetaApiError, MetaParseError)) else (
            f"{type(error).__name__} during sync"
        )
        with engine.begin() as connection:
            connection.execute(
                text("""
                    UPDATE meta_insight_sync_runs
                    SET status = 'FAILED', finished_at = NOW(), error_summary = :summary,
                        attempt_count = :attempts, usage_headers = CAST(:usage AS JSONB)
                    WHERE id = :id
                """),
                {
                    "id": run_id, "summary": summary[:500], "attempts": client.attempts,
                    "usage": json.dumps(client.usage),
                },
            )
        raise
    return run_id


def _upsert_account(engine: Engine, ad_account_id: str, account: dict) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO meta_ad_accounts (
                    ad_account_id, name, currency, timezone_name,
                    timezone_offset_hours_utc, raw_metadata, last_seen_at
                ) VALUES (
                    :id, :name, :currency, :tz, :offset, CAST(:raw AS JSONB), NOW()
                )
                ON CONFLICT (ad_account_id) DO UPDATE SET
                    name = EXCLUDED.name, currency = EXCLUDED.currency,
                    timezone_name = EXCLUDED.timezone_name,
                    timezone_offset_hours_utc = EXCLUDED.timezone_offset_hours_utc,
                    raw_metadata = EXCLUDED.raw_metadata, last_seen_at = NOW()
            """),
            {
                "id": ad_account_id, "name": account.get("name"),
                "currency": account.get("currency"), "tz": account.get("timezone_name"),
                "offset": to_decimal(account.get("timezone_offset_hours_utc")),
                "raw": json.dumps(account),
            },
        )


def _land_page(engine: Engine, run_id: UUID, rows: list[dict]) -> None:
    with engine.begin() as connection:
        for row in rows:
            payload = json.dumps(row, sort_keys=True, separators=(",", ":"))
            connection.execute(
                text("""
                    INSERT INTO raw_meta_insights (
                        sync_run_id, reporting_date, ad_id, payload, payload_hash
                    ) VALUES (:run, :day, :ad, CAST(:payload AS JSONB), :hash)
                    ON CONFLICT (sync_run_id, payload_hash) DO NOTHING
                """),
                {
                    "run": run_id, "day": row.get("date_start"), "ad": str(row.get("ad_id")),
                    "payload": payload, "hash": hashlib.sha256(payload.encode()).hexdigest(),
                },
            )
        connection.execute(
            text("""
                UPDATE meta_insight_sync_runs
                SET page_count = page_count + 1, row_count = row_count + :rows
                WHERE id = :id
            """),
            {"id": run_id, "rows": len(rows)},
        )


def normalize_run(connection: Connection, run_id: UUID, account: dict) -> object:
    """Rebuild facts for the run's range from its raw rows. Returns normalized spend."""
    run = connection.execute(
        text("""
            SELECT ad_account_id, date_from, date_to, attribution_key,
                attribution_windows, action_report_time
            FROM meta_insight_sync_runs WHERE id = :id
        """),
        {"id": run_id},
    ).mappings().one()
    raw_rows = connection.execute(
        text("SELECT payload, fetched_at FROM raw_meta_insights WHERE sync_run_id = :id"),
        {"id": run_id},
    ).all()
    connection.execute(
        text("""
            DELETE FROM meta_ad_daily_performance
            WHERE ad_account_id = :account AND attribution_key = :key
              AND reporting_date BETWEEN :date_from AND :date_to
        """),
        {
            "account": run["ad_account_id"], "key": run["attribution_key"],
            "date_from": run["date_from"], "date_to": run["date_to"],
        },
    )
    seen: set[tuple[str, date]] = set()
    for payload, fetched_at in raw_rows:
        row = parse_insight_row(payload)
        if (row.ad_id, row.reporting_date) in seen:
            raise MetaParseError("Meta returned two different rows for one ad and day")
        seen.add((row.ad_id, row.reporting_date))
        if row.ad_account_id != run["ad_account_id"]:
            raise MetaParseError("Insight row belongs to a different ad account")
        if not run["date_from"] <= row.reporting_date <= run["date_to"]:
            raise MetaParseError("Insight row is outside the requested date range")
        _upsert_dimensions(connection, row)
        _upsert_fact(connection, run_id, run, row, fetched_at, account)
    return connection.execute(
        text("""
            SELECT COALESCE(sum(spend), 0) FROM meta_ad_daily_performance
            WHERE ad_account_id = :account AND attribution_key = :key
              AND reporting_date BETWEEN :date_from AND :date_to
        """),
        {
            "account": run["ad_account_id"], "key": run["attribution_key"],
            "date_from": run["date_from"], "date_to": run["date_to"],
        },
    ).scalar_one()


def _upsert_dimensions(connection: Connection, row) -> None:
    connection.execute(
        text("""
            INSERT INTO meta_campaigns (campaign_id, ad_account_id, name, objective)
            VALUES (:campaign, :account, :name, :objective)
            ON CONFLICT (campaign_id) DO UPDATE SET
                name = COALESCE(EXCLUDED.name, meta_campaigns.name),
                objective = COALESCE(EXCLUDED.objective, meta_campaigns.objective),
                last_seen_at = NOW()
        """),
        {
            "campaign": row.campaign_id, "account": row.ad_account_id,
            "name": row.campaign_name, "objective": row.objective,
        },
    )
    connection.execute(
        text("""
            INSERT INTO meta_ad_sets (ad_set_id, campaign_id, ad_account_id, name)
            VALUES (:ad_set, :campaign, :account, :name)
            ON CONFLICT (ad_set_id) DO UPDATE SET
                name = COALESCE(EXCLUDED.name, meta_ad_sets.name), last_seen_at = NOW()
        """),
        {
            "ad_set": row.ad_set_id, "campaign": row.campaign_id,
            "account": row.ad_account_id, "name": row.ad_set_name,
        },
    )
    connection.execute(
        text("""
            INSERT INTO meta_ads (ad_id, ad_set_id, campaign_id, ad_account_id, name)
            VALUES (:ad, :ad_set, :campaign, :account, :name)
            ON CONFLICT (ad_id) DO UPDATE SET
                name = COALESCE(EXCLUDED.name, meta_ads.name), last_seen_at = NOW()
        """),
        {
            "ad": row.ad_id, "ad_set": row.ad_set_id, "campaign": row.campaign_id,
            "account": row.ad_account_id, "name": row.ad_name,
        },
    )


def _upsert_fact(connection: Connection, run_id, run, row, fetched_at, account: dict) -> None:
    connection.execute(
        text("""
            INSERT INTO meta_ad_daily_performance (
                ad_account_id, campaign_id, ad_set_id, ad_id, reporting_date,
                attribution_key, attribution_windows, action_report_time,
                currency, timezone_name, spend, impressions, reach, clicks,
                link_clicks, outbound_clicks, landing_page_views, add_to_cart,
                checkouts_initiated, purchases, purchase_value, leads,
                actions, action_values, unclassified_action_types,
                source_sync_run_id, fetched_at, updated_at
            ) VALUES (
                :account, :campaign, :ad_set, :ad, :day,
                :key, :windows, :report_time,
                :currency, :tz, :spend, :impressions, :reach, :clicks,
                :link_clicks, :outbound_clicks, :landing_page_views, :add_to_cart,
                :checkouts, :purchases, :purchase_value, :leads,
                CAST(:actions AS JSONB), CAST(:action_values AS JSONB), :unclassified,
                :run, :fetched_at, NOW()
            )
        """),
        {
            "account": row.ad_account_id, "campaign": row.campaign_id,
            "ad_set": row.ad_set_id, "ad": row.ad_id, "day": row.reporting_date,
            "key": run["attribution_key"], "windows": run["attribution_windows"],
            "report_time": run["action_report_time"],
            "currency": row.currency or account.get("currency"),
            "tz": account.get("timezone_name"),
            "spend": row.spend, "impressions": row.impressions, "reach": row.reach,
            "clicks": row.clicks, "link_clicks": row.link_clicks,
            "outbound_clicks": row.outbound_clicks,
            "landing_page_views": row.landing_page_views, "add_to_cart": row.add_to_cart,
            "checkouts": row.checkouts_initiated, "purchases": row.purchases,
            "purchase_value": row.purchase_value, "leads": row.leads,
            "actions": json.dumps(row.actions), "action_values": json.dumps(row.action_values),
            "unclassified": row.unclassified_action_types, "run": run_id,
            "fetched_at": fetched_at,
        },
    )
