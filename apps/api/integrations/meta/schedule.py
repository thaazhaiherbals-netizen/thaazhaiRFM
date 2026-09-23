"""Daily scheduled Meta sync: re-fetch the lookback window through yesterday.

The decision is derived from sync-run history, not in-memory state, so it survives
restarts, catches up if the host was off at the scheduled time, never repeats a day
that already succeeded, and backs off between failed attempts.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Engine, text

from apps.api.config import Settings
from apps.api.integrations.meta.client import MetaApiError, MetaClient
from apps.api.integrations.meta.sync import SyncInProgress, recent_window, run_sync

logger = logging.getLogger("thaazhai.meta_scheduler")
MAX_ATTEMPTS_PER_DAY = 3
RETRY_AFTER = timedelta(minutes=30)
Decision = Literal["run", "wait", "done", "backoff", "gave_up"]


@dataclass(frozen=True)
class RunSummary:
    status: str
    started_at: datetime


def decide(
    local_now: datetime, sync_time: time, todays_runs: list[RunSummary],
    max_attempts: int = MAX_ATTEMPTS_PER_DAY, retry_after: timedelta = RETRY_AFTER,
) -> Decision:
    """`todays_runs` are SCHEDULED runs whose window ends yesterday (account-local)."""
    if any(run.status == "SUCCEEDED" for run in todays_runs):
        return "done"
    if local_now.time() < sync_time:
        return "wait"
    attempts = [run for run in todays_runs if run.status in ("FAILED", "RUNNING")]
    if len(attempts) >= max_attempts:
        return "gave_up"
    if attempts and local_now - max(run.started_at for run in attempts) < retry_after:
        return "backoff"
    return "run"


def account_zone(name: str | None, offset_hours: object = None) -> timezone | ZoneInfo:
    if name:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            pass
    try:
        return timezone(timedelta(hours=float(offset_hours))) if offset_hours is not None else (
            timezone.utc
        )
    except (TypeError, ValueError):
        return timezone.utc


def run_scheduled_once(
    engine: Engine,
    settings: Settings,
    client_factory: Callable[[], MetaClient],
    now: datetime | None = None,
) -> Decision:
    """One scheduler tick. Returns what it decided (and did)."""
    with engine.connect() as connection:
        account = connection.execute(
            text("""
                SELECT timezone_name, timezone_offset_hours_utc FROM meta_ad_accounts
                WHERE ad_account_id = :id
            """),
            {"id": settings.meta_ad_account_id},
        ).first()
    client = client_factory()
    try:
        if account is None:
            # First ever run: learn the account timezone before deciding "yesterday".
            info = client.get_account()
            zone = account_zone(info.get("timezone_name"), info.get("timezone_offset_hours_utc"))
        else:
            zone = account_zone(account.timezone_name, account.timezone_offset_hours_utc)
        local_now = (now or datetime.now(timezone.utc)).astimezone(zone)
        date_from, date_to = recent_window(settings.meta_sync_lookback_days, local_now.date())
        with engine.connect() as connection:
            runs = [
                RunSummary(row.status, row.started_at.astimezone(zone))
                for row in connection.execute(
                    text("""
                        SELECT status, started_at FROM meta_insight_sync_runs
                        WHERE ad_account_id = :account AND trigger = 'SCHEDULED'
                          AND date_to = :date_to
                    """),
                    {"account": settings.meta_ad_account_id, "date_to": date_to},
                )
            ]
        decision = decide(local_now, settings.meta_sync_time, runs)
        if decision != "run":
            return decision
        logger.info('{"event":"meta_scheduled_sync_start","from":"%s","to":"%s"}',
                    date_from, date_to)
        try:
            run_sync(
                engine, client,
                ad_account_id=settings.meta_ad_account_id,
                api_version=settings.meta_graph_api_version,
                date_from=date_from, date_to=date_to,
                windows=settings.meta_attribution_windows,
                report_time=settings.meta_action_report_time,
                trigger="SCHEDULED",
            )
        except SyncInProgress:
            return "backoff"
        except MetaApiError as error:
            # The run row already holds the sanitized reason; the token is never logged.
            logger.error('{"event":"meta_scheduled_sync_failed","error":"%s"}', str(error)[:200])
            return "backoff"
        logger.info('{"event":"meta_scheduled_sync_succeeded"}')
        return "run"
    finally:
        client.close()
