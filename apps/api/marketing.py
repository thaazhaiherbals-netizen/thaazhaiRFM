"""Read-only Meta marketing reports and manual sync (docs/META_MARKETING_INTEGRATION.md).

Reports read canonical ad/day facts for ONE attribution configuration, so campaign,
ad-set and account totals are plain sums of the same rows (no cross-level double
counting). Ratios are computed from summed numerators/denominators, never averaged.
Meta-attributed conversions are kept apart from observed business orders; blended
metrics are date-level only and do not attribute individual orders to campaigns.
"""

import json
import logging
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from pydantic import BaseModel, model_validator
from sqlalchemy import text

from apps.api.admin import Page, paged
from apps.api.auth import require_admin
from apps.api.config import get_settings
from apps.api.db import get_engine
from apps.api.integrations.meta.client import MetaApiError, MetaClient
from apps.api.integrations.meta.sync import (
    InvalidSyncRange,
    SyncInProgress,
    attribution_key,
    chunks,
    run_sync,
    validate_range,
)

logger = logging.getLogger("thaazhai.marketing")
router = APIRouter(
    prefix="/admin/marketing", dependencies=[Depends(require_admin)], tags=["Marketing"]
)
MAX_REPORT_DAYS = 400
MANUAL_SYNC_MAX_DAYS = 31

# Summed facts plus ratios from summed parts. `reach` is per ad per day, so its sum is
# NOT unique reach; it is exposed only as reach_daily_sum / average daily frequency.
TOTALS_SQL = """
    COALESCE(sum(f.spend), 0) AS spend,
    COALESCE(sum(f.impressions), 0) AS impressions,
    COALESCE(sum(f.reach), 0) AS reach_daily_sum,
    COALESCE(sum(f.clicks), 0) AS clicks,
    COALESCE(sum(f.link_clicks), 0) AS link_clicks,
    COALESCE(sum(f.outbound_clicks), 0) AS outbound_clicks,
    COALESCE(sum(f.landing_page_views), 0) AS landing_page_views,
    COALESCE(sum(f.add_to_cart), 0) AS add_to_cart,
    COALESCE(sum(f.checkouts_initiated), 0) AS checkouts_initiated,
    COALESCE(sum(f.purchases), 0) AS meta_purchases,
    COALESCE(sum(f.purchase_value), 0) AS meta_purchase_value,
    COALESCE(sum(f.leads), 0) AS leads,
    round(sum(f.spend) / NULLIF(sum(f.impressions), 0) * 1000, 2) AS cpm,
    round(sum(f.link_clicks)::NUMERIC / NULLIF(sum(f.impressions), 0) * 100, 2) AS ctr,
    round(sum(f.spend) / NULLIF(sum(f.link_clicks), 0), 2) AS cpc,
    round(sum(f.impressions)::NUMERIC / NULLIF(sum(f.reach), 0), 2) AS avg_daily_frequency,
    round(sum(f.purchase_value) / NULLIF(sum(f.spend), 0), 2) AS meta_roas,
    round(sum(f.spend) / NULLIF(sum(f.purchases), 0), 2) AS cost_per_meta_purchase
"""
CampaignSort = Literal[
    "spend", "impressions", "link_clicks", "ctr", "cpc", "cpm",
    "meta_purchases", "meta_roas", "name",
]


def ratio(numerator, denominator) -> Decimal | None:
    """Money-style 2dp ratio rounded half-up, matching PostgreSQL round(); NULL on zero."""
    if not denominator:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


class SyncRequest(BaseModel):
    date_from: date
    date_to: date

    @model_validator(mode="after")
    def bounded(self) -> "SyncRequest":
        if self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        if (self.date_to - self.date_from).days + 1 > MAX_REPORT_DAYS:
            raise ValueError(f"Sync covers at most {MAX_REPORT_DAYS} days at a time")
        return self


def report_range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    date_to = date_to or date.today() - timedelta(days=1)
    date_from = date_from or date_to - timedelta(days=29)
    if date_from > date_to:
        raise HTTPException(422, "date_from must be on or before date_to")
    if (date_to - date_from).days + 1 > MAX_REPORT_DAYS:
        raise HTTPException(422, f"Report range is limited to {MAX_REPORT_DAYS} days")
    return date_from, date_to


def reporting_context(connection) -> dict:
    """Pick the attribution configuration to report, plus account labels and freshness."""
    settings = get_settings()
    key = None
    if settings.meta_configured:
        key = attribution_key(settings.meta_attribution_windows, settings.meta_action_report_time)
    latest_success = connection.execute(
        text("""
            SELECT r.ad_account_id, r.attribution_key, r.attribution_windows,
                r.action_report_time, r.finished_at, r.date_to
            FROM meta_insight_sync_runs r
            WHERE r.status = 'SUCCEEDED'
              AND (CAST(:key AS TEXT) IS NULL OR r.attribution_key = :key)
            ORDER BY r.finished_at DESC LIMIT 1
        """),
        {"key": key},
    ).mappings().first()
    latest_run = connection.execute(
        text("""
            SELECT id, status, trigger, date_from, date_to, started_at, finished_at,
                error_summary
            FROM meta_insight_sync_runs ORDER BY started_at DESC LIMIT 1
        """)
    ).mappings().first()
    key = key or (latest_success["attribution_key"] if latest_success else None)
    account_id = settings.meta_ad_account_id or (
        latest_success["ad_account_id"] if latest_success else None
    )
    account = None
    if account_id:
        account = connection.execute(
            text("""
                SELECT ad_account_id, name, currency, timezone_name
                FROM meta_ad_accounts WHERE ad_account_id = :id
            """),
            {"id": account_id},
        ).mappings().first()
    last_data_date = None
    if key:
        last_data_date = connection.execute(
            text("""
                SELECT max(reporting_date) FROM meta_ad_daily_performance
                WHERE attribution_key = :key
                  AND (CAST(:account AS TEXT) IS NULL OR ad_account_id = :account)
            """),
            {"key": key, "account": account_id},
        ).scalar_one()
    return {
        "configured": settings.meta_configured,
        "attribution_key": key,
        "account_id": account_id,
        "account": dict(account) if account else None,
        "last_successful_sync": dict(latest_success) if latest_success else None,
        "latest_run": dict(latest_run) if latest_run else None,
        "last_data_date": last_data_date,
    }


def fact_scope(context: dict) -> tuple[str, dict]:
    return (
        "f.attribution_key = :key AND f.ad_account_id = :account "
        "AND f.reporting_date BETWEEN :date_from AND :date_to",
        {"key": context["attribution_key"], "account": context["account_id"]},
    )


@router.get("/overview")
def overview(date_from: date | None = None, date_to: date | None = None) -> dict:
    date_from, date_to = report_range(date_from, date_to)
    with get_engine().connect() as connection:
        context = reporting_context(connection)
        where, params = fact_scope(context)
        params |= {"date_from": date_from, "date_to": date_to}
        meta = dict(connection.execute(
            text(f"SELECT {TOTALS_SQL} FROM meta_ad_daily_performance f WHERE {where}"), params
        ).mappings().one())
        # Business facts come from orders/customers only (no line-item fanout).
        business = dict(connection.execute(
            text("""
                SELECT
                    (SELECT count(*) FROM orders
                        WHERE order_date BETWEEN :date_from AND :date_to) AS orders,
                    (SELECT COALESCE(sum(order_value), 0) FROM orders
                        WHERE order_date BETWEEN :date_from AND :date_to) AS revenue,
                    (SELECT count(*) FROM customers
                        WHERE first_order_date BETWEEN :date_from AND :date_to)
                        AS new_customers
            """),
            {"date_from": date_from, "date_to": date_to},
        ).mappings().one())
        spend = meta["spend"]
        blended = {
            "mer": ratio(business["revenue"], spend),
            "spend_per_order": ratio(spend, business["orders"]),
            "new_customer_cac": ratio(spend, business["new_customers"]),
        }
        daily = connection.execute(
            text(f"""
                WITH days AS (
                    SELECT generate_series(CAST(:date_from AS DATE), CAST(:date_to AS DATE),
                        INTERVAL '1 day')::DATE AS day
                ),
                meta AS (
                    SELECT f.reporting_date AS day, sum(f.spend) AS spend,
                        sum(f.impressions) AS impressions, sum(f.link_clicks) AS link_clicks,
                        sum(f.purchases) AS meta_purchases,
                        sum(f.purchase_value) AS meta_purchase_value
                    FROM meta_ad_daily_performance f WHERE {where}
                    GROUP BY f.reporting_date
                ),
                business AS (
                    SELECT order_date AS day, count(*) AS orders, sum(order_value) AS revenue
                    FROM orders WHERE order_date BETWEEN :date_from AND :date_to
                    GROUP BY order_date
                )
                SELECT d.day, COALESCE(m.spend, 0) AS spend,
                    COALESCE(m.impressions, 0) AS impressions,
                    COALESCE(m.link_clicks, 0) AS link_clicks,
                    COALESCE(m.meta_purchases, 0) AS meta_purchases,
                    COALESCE(m.meta_purchase_value, 0) AS meta_purchase_value,
                    COALESCE(b.orders, 0) AS orders, COALESCE(b.revenue, 0) AS revenue
                FROM days d
                LEFT JOIN meta m ON m.day = d.day
                LEFT JOIN business b ON b.day = d.day
                ORDER BY d.day
            """),
            params,
        ).mappings().all()
        unclassified = connection.execute(
            text(f"""
                SELECT action_type, count(*) AS rows
                FROM meta_ad_daily_performance f,
                    unnest(f.unclassified_action_types) AS action_type
                WHERE {where}
                GROUP BY action_type ORDER BY rows DESC, action_type LIMIT 50
            """),
            params,
        ).mappings().all()
        # A day counts as synced when a successful run for this account and attribution
        # covered it; days with no spend legitimately have no fact rows.
        coverage = dict(connection.execute(
            text("""
                WITH days AS (
                    SELECT generate_series(CAST(:date_from AS DATE), CAST(:date_to AS DATE),
                        INTERVAL '1 day')::DATE AS day
                ),
                missing AS (
                    SELECT d.day FROM days d
                    WHERE NOT EXISTS (
                        SELECT 1 FROM meta_insight_sync_runs r
                        WHERE r.status = 'SUCCEEDED' AND r.ad_account_id = :account
                          AND r.attribution_key = :key
                          AND d.day BETWEEN r.date_from AND r.date_to
                    )
                )
                SELECT (SELECT count(*) FROM days) AS total_days,
                    (SELECT count(*) FROM missing) AS unsynced_days,
                    (SELECT min(day) FROM missing) AS first_unsynced,
                    (SELECT max(day) FROM missing) AS last_unsynced
            """),
            params,
        ).mappings().one())
    return {
        "date_from": date_from,
        "date_to": date_to,
        "context": context,
        "is_stale": coverage["unsynced_days"] > 0,
        "coverage": coverage,
        "meta": meta,
        "business": business,
        "blended": blended,
        "daily": [dict(row) for row in daily],
        "unclassified_actions": [dict(row) for row in unclassified],
    }


def grouped(level: Literal["campaign", "ad_set", "ad"], parent: str | None = None) -> str:
    """Totals per dimension; the WHERE clause is filled in via ``.format(where=...)``."""
    table, column = {
        "campaign": ("meta_campaigns", "campaign_id"),
        "ad_set": ("meta_ad_sets", "ad_set_id"),
        "ad": ("meta_ads", "ad_id"),
    }[level]
    objective = "d.objective" if level == "campaign" else "NULL::TEXT"
    parent_select = f"f.{parent} AS parent_id, " if parent else ""
    group_by = ", ".join(
        [f"f.{column}", "d.name"]
        + (["d.objective"] if level == "campaign" else [])
        + ([f"f.{parent}"] if parent else [])
    )
    return f"""
        SELECT {parent_select}f.{column} AS id, COALESCE(d.name, f.{column}) AS name,
            {objective} AS objective, {TOTALS_SQL}
        FROM meta_ad_daily_performance f
        LEFT JOIN {table} d ON d.{column} = f.{column}
        WHERE {{where}}
        GROUP BY {group_by}
    """


@router.get("/campaigns", response_model=Page)
def campaigns(
    date_from: date | None = None,
    date_to: date | None = None,
    sort: CampaignSort = "spend",
    direction: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Page:
    date_from, date_to = report_range(date_from, date_to)
    with get_engine().connect() as connection:
        context = reporting_context(connection)
    where, params = fact_scope(context)
    sql = grouped("campaign").format(where=where)
    # `sort`/`direction` are Literal-validated, so interpolation is safe.
    order = f" ORDER BY {sort} {direction.upper()} NULLS LAST, id"
    return paged(
        sql + order, params | {"date_from": date_from, "date_to": date_to}, limit, offset
    )


@router.get("/campaigns/{campaign_id}")
def campaign_detail(
    campaign_id: str, date_from: date | None = None, date_to: date | None = None
) -> dict:
    date_from, date_to = report_range(date_from, date_to)
    with get_engine().connect() as connection:
        campaign = connection.execute(
            text("""
                SELECT campaign_id, name, status, objective, ad_account_id, last_seen_at
                FROM meta_campaigns WHERE campaign_id = :id
            """),
            {"id": campaign_id},
        ).mappings().first()
        if campaign is None:
            raise HTTPException(404, "Campaign not found")
        context = reporting_context(connection)
        where, params = fact_scope(context)
        params |= {"date_from": date_from, "date_to": date_to, "campaign_id": campaign_id}
        scope = where + " AND f.campaign_id = :campaign_id"
        totals = connection.execute(
            text(f"SELECT {TOTALS_SQL} FROM meta_ad_daily_performance f WHERE {scope}"),
            params,
        ).mappings().one()
        ad_sets = connection.execute(
            text(grouped("ad_set").format(where=scope) + " ORDER BY spend DESC, id"), params
        ).mappings().all()
        ads = connection.execute(
            text(grouped("ad", "ad_set_id").format(where=scope) + " ORDER BY spend DESC, id"),
            params,
        ).mappings().all()
    return {
        "date_from": date_from,
        "date_to": date_to,
        "campaign": dict(campaign),
        "totals": dict(totals),
        "ad_sets": [dict(row) for row in ad_sets],
        "ads": [dict(row) for row in ads],
    }


@router.get("/sync-runs", response_model=Page)
def sync_runs(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)) -> Page:
    return paged(
        """
        SELECT id, ad_account_id, trigger, date_from, date_to, status, attribution_key,
            api_version, page_count, row_count, attempt_count, normalized_spend,
            control_spend, normalized_spend - control_spend AS control_difference,
            error_summary, started_at, finished_at
        FROM meta_insight_sync_runs ORDER BY started_at DESC
        """,
        {},
        limit,
        offset,
    )


def build_client() -> MetaClient:
    settings = get_settings()
    if not settings.meta_configured:
        raise HTTPException(503, "Meta Marketing API is not configured")
    return MetaClient(
        settings.meta_ad_account_id,
        settings.meta_access_token.get_secret_value(),
        settings.meta_graph_api_version,
    )


def _sync_chunk(client: MetaClient, date_from: date, date_to: date, trigger: str) -> UUID:
    settings = get_settings()
    return run_sync(
        get_engine(), client,
        ad_account_id=settings.meta_ad_account_id,
        api_version=settings.meta_graph_api_version,
        date_from=date_from, date_to=date_to,
        windows=settings.meta_attribution_windows,
        report_time=settings.meta_action_report_time,
        trigger=trigger,
        # Meta recommends async report runs for larger ranges.
        use_async=(date_to - date_from).days + 1 > 7,
    )


def _background_sync(ranges: list[tuple[date, date]]) -> None:
    """Runs after the response; each chunk records its own run row (progress/errors)."""
    client = build_client()
    try:
        for date_from, date_to in ranges:
            try:
                _sync_chunk(client, date_from, date_to, "MANUAL")
            except Exception as error:  # Run row already holds the sanitized reason.
                logger.warning(json.dumps({
                    "event": "meta_background_sync_stopped", "type": type(error).__name__,
                    "date_from": str(date_from), "date_to": str(date_to),
                }))
                return
    finally:
        client.close()


@router.post("/sync", status_code=201)
def sync(request: SyncRequest, background: BackgroundTasks, response: Response) -> dict:
    """Manual re-fetch. Up to 31 days runs inline; longer ranges run in the background
    in 31-day chunks, visible in /sync-runs. Rerunning dates replaces their facts."""
    client = build_client()
    settings = get_settings()
    try:
        validate_range(request.date_from, request.date_to, max_days=MAX_REPORT_DAYS)
    except InvalidSyncRange as error:
        client.close()
        raise HTTPException(422, str(error)) from None
    with get_engine().connect() as connection:
        running = connection.execute(
            text("""
                SELECT 1 FROM meta_insight_sync_runs
                WHERE ad_account_id = :account AND status = 'RUNNING'
                  AND started_at > NOW() - INTERVAL '2 hours'
            """),
            {"account": settings.meta_ad_account_id},
        ).first()
    if running:
        client.close()
        raise HTTPException(409, "A Meta sync is already running; try again when it finishes")

    ranges = list(chunks(request.date_from, request.date_to, MANUAL_SYNC_MAX_DAYS))
    if len(ranges) > 1:
        client.close()
        background.add_task(_background_sync, ranges)
        response.status_code = 202
        return {
            "status": "STARTED", "mode": "background", "chunks": len(ranges),
            "date_from": request.date_from, "date_to": request.date_to,
        }
    try:
        run_id = _sync_chunk(client, request.date_from, request.date_to, "MANUAL")
    except SyncInProgress as error:
        raise HTTPException(409, str(error)) from None
    except MetaApiError as error:
        raise HTTPException(502, f"Meta sync failed: {error}") from None
    finally:
        client.close()
    with get_engine().connect() as connection:
        run = connection.execute(
            text("""
                SELECT id, status, page_count, row_count, normalized_spend, control_spend,
                    started_at, finished_at
                FROM meta_insight_sync_runs WHERE id = :id
            """),
            {"id": run_id},
        ).mappings().one()
    return {**dict(run), "mode": "inline"}
