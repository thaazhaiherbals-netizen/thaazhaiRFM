"""Meta sync + marketing reports against a disposable *_check PostgreSQL. No network."""

import copy
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_order_processing import engine as engine
from test_order_processing import insert_raw, payload

from apps.api import marketing
from apps.api.config import get_settings
from apps.api.integrations.meta.client import MetaApiError, MetaClient
from apps.api.integrations.meta.sync import SyncInProgress, run_sync
from apps.api.main import app
from apps.api.order_processing import process_single_order

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_TESTS") != "1", reason="Needs disposable PostgreSQL"
)

FIXTURES = Path(__file__).parent / "fixtures" / "meta"
TOKEN = "fixture-secret-token-do-not-log"
WINDOWS = ["1d_view", "7d_click"]
ACCOUNT = {
    "account_id": "1111111111", "name": "Synthetic Account", "currency": "INR",
    "timezone_name": "Asia/Kolkata", "timezone_offset_hours_utc": 5.5,
}


def pages() -> dict:
    return {
        None: json.loads((FIXTURES / "insights_page_1.json").read_text(encoding="utf-8")),
        "AFTER1": json.loads((FIXTURES / "insights_page_2.json").read_text(encoding="utf-8")),
    }


def fake_meta(page_map: dict, control_spend: str = "1751.49", fail_after: str | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v23.0/act_1111111111":
            return httpx.Response(200, json=ACCOUNT)
        if request.url.params.get("level") == "account":
            return httpx.Response(200, json={"data": [{"spend": control_spend}]})
        after = request.url.params.get("after")
        if fail_after is not None and after == fail_after:
            return httpx.Response(400, json={"error": {
                "code": 190, "message": f"Error validating access token {TOKEN}",
            }})
        return httpx.Response(200, json=page_map[after])

    return MetaClient(
        "1111111111", TOKEN, "v23.0",
        http=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _: None,
    )


def sync(engine, client, date_to=date(2026, 9, 2)):
    return run_sync(
        engine, client, ad_account_id="1111111111", api_version="v23.0",
        date_from=date(2026, 9, 1), date_to=date_to, windows=WINDOWS,
        report_time="conversion",
    )


@pytest.fixture
def meta_engine(engine):
    with engine.begin() as connection:
        connection.execute(text(
            "TRUNCATE meta_ad_daily_performance, raw_meta_insights, meta_insight_sync_runs, "
            "meta_ads, meta_ad_sets, meta_campaigns, meta_ad_accounts CASCADE"
        ))
    return engine


def scalar(engine, sql, **params):
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def one(engine, sql, **params):
    # Always close the connection: an idle-in-transaction reader blocks later TRUNCATEs.
    with engine.connect() as connection:
        return dict(connection.execute(text(sql), params).mappings().one())


def test_sync_lands_raw_and_normalizes_canonical_facts(meta_engine):
    run_id = sync(meta_engine, fake_meta(pages()))
    run = one(meta_engine, "SELECT * FROM meta_insight_sync_runs WHERE id = :id", id=run_id)
    assert run["status"] == "SUCCEEDED"
    assert (run["page_count"], run["row_count"]) == (2, 3)
    assert run["normalized_spend"] == run["control_spend"] == Decimal("1751.49")
    assert TOKEN not in json.dumps(run, default=str)
    assert scalar(meta_engine, "SELECT count(*) FROM raw_meta_insights") == 3
    assert scalar(meta_engine, "SELECT count(*) FROM meta_ad_daily_performance") == 3
    assert scalar(meta_engine, "SELECT sum(purchases) FROM meta_ad_daily_performance") == 13
    assert scalar(
        meta_engine, "SELECT timezone_name FROM meta_ad_daily_performance LIMIT 1"
    ) == "Asia/Kolkata"
    assert scalar(meta_engine, "SELECT count(*) FROM meta_campaigns") == 2
    # Campaign totals reconcile to canonical ad-level facts.
    assert scalar(meta_engine, """
        SELECT count(*) FROM (
            SELECT campaign_id, sum(spend) s FROM meta_ad_daily_performance GROUP BY 1
        ) c
    """) == 2


def test_rerun_is_idempotent_and_raw_history_is_append_only(meta_engine):
    sync(meta_engine, fake_meta(pages()))
    sync(meta_engine, fake_meta(pages()))
    assert scalar(meta_engine, "SELECT sum(spend) FROM meta_ad_daily_performance") == Decimal(
        "1751.49"
    )
    assert scalar(meta_engine, "SELECT count(*) FROM meta_ad_daily_performance") == 3
    assert scalar(meta_engine, "SELECT count(*) FROM raw_meta_insights") == 6


def test_restatement_updates_facts_and_drops_withdrawn_rows(meta_engine):
    sync(meta_engine, fake_meta(pages()))
    restated = pages()
    restated[None]["data"][0]["spend"] = "1300.00"
    restated[None]["data"][0]["actions"][6]["value"] = "9"  # omni_purchase
    del restated[None]["data"][1]  # ad 4002 withdrawn for that day
    sync(meta_engine, fake_meta(restated, control_spend="1800.00"))
    assert scalar(meta_engine, "SELECT count(*) FROM meta_ad_daily_performance") == 2
    assert scalar(meta_engine, "SELECT sum(spend) FROM meta_ad_daily_performance") == Decimal(
        "1800.00"
    )
    assert scalar(
        meta_engine, "SELECT purchases FROM meta_ad_daily_performance WHERE ad_id = '4001'"
    ) == 9
    assert scalar(meta_engine, "SELECT count(*) FROM raw_meta_insights") == 5


def test_dimension_names_change_but_join_by_id(meta_engine):
    sync(meta_engine, fake_meta(pages()))
    renamed = pages()
    for row in renamed[None]["data"]:
        row["campaign_name"] = "Renamed Campaign"
    sync(meta_engine, fake_meta(renamed))
    assert scalar(
        meta_engine, "SELECT name FROM meta_campaigns WHERE campaign_id = '2001'"
    ) == "Renamed Campaign"
    assert scalar(meta_engine, "SELECT count(*) FROM meta_campaigns") == 2


def test_failed_page_marks_run_failed_and_keeps_previous_facts(meta_engine):
    sync(meta_engine, fake_meta(pages()))
    changed = copy.deepcopy(pages())
    changed[None]["data"][0]["spend"] = "9999.00"
    with pytest.raises(MetaApiError):
        sync(meta_engine, fake_meta(changed, fail_after="AFTER1"))
    failed = one(
        meta_engine,
        "SELECT status, error_summary FROM meta_insight_sync_runs "
        "ORDER BY started_at DESC LIMIT 1",
    )
    assert failed["status"] == "FAILED"
    assert TOKEN not in failed["error_summary"]
    assert scalar(meta_engine, "SELECT sum(spend) FROM meta_ad_daily_performance") == Decimal(
        "1751.49"
    )


def test_overlapping_runs_are_rejected(meta_engine):
    with meta_engine.connect() as holder:
        holder.execute(text(
            "SELECT pg_advisory_lock(hashtextextended('meta_insights_sync:1111111111', 0))"
        ))
        with pytest.raises(SyncInProgress):
            sync(meta_engine, fake_meta(pages()))
        holder.execute(text(
            "SELECT pg_advisory_unlock(hashtextextended('meta_insights_sync:1111111111', 0))"
        ))


def test_overview_blends_meta_with_orders_without_item_fanout(meta_engine, monkeypatch):
    sync(meta_engine, fake_meta(pages()))
    for index, day in enumerate(["September 1, 2026", "September 2, 2026"]):
        raw_id = insert_raw(meta_engine, payload(
            f"meta-{index}", order_date=day, total=875, phone=f"98765432{index}0",
        ))
        assert process_single_order(meta_engine, raw_id).status == "PROCESSED"
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-token-only")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "1111111111")
    monkeypatch.setenv("META_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v23.0")
    monkeypatch.setenv("META_ATTRIBUTION_WINDOWS", json.dumps(WINDOWS))
    get_settings.cache_clear()
    monkeypatch.setattr(marketing, "get_engine", lambda: meta_engine)
    from apps.api import admin

    monkeypatch.setattr(admin, "get_engine", lambda: meta_engine)
    client = TestClient(app, headers={"Authorization": "Bearer test-token-only"})

    body = client.get(
        "/admin/marketing/overview?date_from=2026-09-01&date_to=2026-09-02"
    ).json()
    assert TOKEN not in json.dumps(body)
    assert Decimal(str(body["meta"]["spend"])) == Decimal("1751.49")
    assert Decimal(str(body["business"]["revenue"])) == Decimal("1750.00")
    assert body["business"]["orders"] == 2
    assert body["business"]["new_customers"] == 2
    assert Decimal(str(body["blended"]["mer"])) == Decimal("1.00")
    assert Decimal(str(body["blended"]["new_customer_cac"])) == Decimal("875.75")
    assert Decimal(str(body["meta"]["meta_roas"])) == Decimal("4.45")
    assert [row["action_type"] for row in body["unclassified_actions"]] == ["post_engagement"]
    assert len(body["daily"]) == 2
    assert body["is_stale"] is False
    assert body["coverage"]["unsynced_days"] == 0
    wider = client.get("/admin/marketing/overview?date_from=2026-08-30&date_to=2026-09-02").json()
    assert wider["is_stale"] is True
    assert wider["coverage"]["unsynced_days"] == 2
    assert wider["coverage"]["first_unsynced"] == "2026-08-30"
    assert body["context"]["account"]["currency"] == "INR"

    campaigns = client.get(
        "/admin/marketing/campaigns?date_from=2026-09-01&date_to=2026-09-02&sort=spend"
    ).json()
    assert campaigns["total"] == 2
    assert [c["id"] for c in campaigns["items"]] == ["2001", "2002"]
    assert sum(Decimal(str(c["spend"])) for c in campaigns["items"]) == Decimal("1751.49")

    detail = client.get(
        "/admin/marketing/campaigns/2001?date_from=2026-09-01&date_to=2026-09-02"
    ).json()
    assert Decimal(str(detail["totals"]["spend"])) == Decimal("1251.49")
    assert [ad["id"] for ad in detail["ads"]] == ["4001", "4002"]
    assert detail["ads"][0]["parent_id"] == "3001"
    assert client.get("/admin/marketing/campaigns/unknown").status_code == 404

    runs = client.get("/admin/marketing/sync-runs").json()
    assert runs["total"] == 1
    assert Decimal(str(runs["items"][0]["control_difference"])) == 0
    get_settings.cache_clear()


def test_scheduler_tick_syncs_yesterday_once_per_day(meta_engine):
    from datetime import datetime, timezone

    from apps.api.config import Settings
    from apps.api.integrations.meta.schedule import run_scheduled_once

    settings = Settings(
        app_env="test", meta_ad_account_id="1111111111", meta_access_token=TOKEN,
        meta_graph_api_version="v23.0", meta_sync_lookback_days=2,
        meta_attribution_windows=WINDOWS, meta_sync_time="06:00",
    )
    # 2026-09-03 01:00 UTC is 06:30 in Asia/Kolkata, so "yesterday" is 2026-09-02.
    after_six = datetime(2026, 9, 3, 1, 0, tzinfo=timezone.utc)
    before_six = datetime(2026, 9, 3, 0, 0, tzinfo=timezone.utc)
    factory = lambda: fake_meta(pages())  # noqa: E731
    assert run_scheduled_once(meta_engine, settings, factory, now=before_six) == "wait"
    assert run_scheduled_once(meta_engine, settings, factory, now=after_six) == "run"
    assert run_scheduled_once(meta_engine, settings, factory, now=after_six) == "done"
    run = one(meta_engine, "SELECT trigger, date_from, date_to, status FROM meta_insight_sync_runs")
    assert tuple(run.values()) == (
        "SCHEDULED", date(2026, 9, 1), date(2026, 9, 2), "SUCCEEDED"
    )
    assert scalar(meta_engine, "SELECT count(*) FROM meta_ad_daily_performance") == 3


def test_long_manual_sync_runs_in_background_chunks(meta_engine, monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-token-only")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "1111111111")
    monkeypatch.setenv("META_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v23.0")
    get_settings.cache_clear()
    monkeypatch.setattr(marketing, "get_engine", lambda: meta_engine)
    calls = []
    monkeypatch.setattr(
        marketing, "_sync_chunk", lambda client, start, end, trigger: calls.append((start, end))
    )
    client = TestClient(app, headers={"Authorization": "Bearer test-token-only"})
    response = client.post(
        "/admin/marketing/sync", json={"date_from": "2026-03-01", "date_to": "2026-05-10"}
    )
    assert response.status_code == 202
    assert response.json()["chunks"] == 3
    assert calls == [
        (date(2026, 3, 1), date(2026, 3, 31)),
        (date(2026, 4, 1), date(2026, 5, 1)),
        (date(2026, 5, 2), date(2026, 5, 10)),
    ]
    future = client.post(
        "/admin/marketing/sync", json={"date_from": "2026-03-01", "date_to": "2099-01-01"}
    )
    assert future.status_code == 422
    get_settings.cache_clear()
