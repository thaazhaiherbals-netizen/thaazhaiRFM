"""Marketing guards and pure sync helpers that need no database or network."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from apps.api.config import get_settings
from apps.api.integrations.meta.sync import (
    InvalidSyncRange,
    account_today,
    attribution_key,
    chunks,
    recent_window,
    validate_range,
)
from apps.api.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-token-only")
    for name in ("META_AD_ACCOUNT_ID", "META_ACCESS_TOKEN", "META_GRAPH_API_VERSION"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield TestClient(app)
    get_settings.cache_clear()


AUTH = {"Authorization": "Bearer test-token-only"}


def test_marketing_routes_require_admin(client):
    assert client.get("/admin/marketing/overview").status_code == 401
    assert client.post(
        "/admin/marketing/sync", json={"date_from": "2026-09-01", "date_to": "2026-09-02"}
    ).status_code == 401


def test_sync_without_meta_configuration_returns_503(client):
    response = client.post(
        "/admin/marketing/sync",
        json={"date_from": "2026-09-01", "date_to": "2026-09-02"},
        headers=AUTH,
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Meta Marketing API is not configured"


@pytest.mark.parametrize(
    "body",
    [
        {"date_from": "2026-09-01"},
        {"date_from": "yesterday", "date_to": "2026-09-02"},
        {"date_from": "2024-01-01", "date_to": "2026-03-31"},
        {"date_from": "2026-03-10", "date_to": "2026-03-01"},
    ],
)
def test_malformed_or_oversized_sync_requests_fail_safely(client, body):
    assert client.post("/admin/marketing/sync", json=body, headers=AUTH).status_code == 422


def test_report_rejects_reversed_or_malformed_dates(client):
    assert client.get(
        "/admin/marketing/overview?date_from=2026-09-10&date_to=2026-09-01", headers=AUTH
    ).status_code == 422
    assert client.get(
        "/admin/marketing/campaigns?date_from=bad", headers=AUTH
    ).status_code == 422
    assert client.get(
        "/admin/marketing/campaigns?sort=spend;DROP", headers=AUTH
    ).status_code == 422


def test_range_validation_and_chunking():
    today = date(2026, 9, 23)
    with pytest.raises(InvalidSyncRange):
        validate_range(date(2026, 9, 5), date(2026, 9, 1), today)
    with pytest.raises(InvalidSyncRange):
        validate_range(date(2026, 9, 1), date(2026, 9, 24), today)
    with pytest.raises(InvalidSyncRange):
        validate_range(date(2026, 1, 1), date(2026, 6, 1), today)
    assert list(chunks(date(2026, 1, 1), date(2026, 2, 5), 31)) == [
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 5)),
    ]


def test_recent_window_ends_yesterday_and_key_is_order_independent():
    assert recent_window(7, date(2026, 9, 23)) == (date(2026, 9, 16), date(2026, 9, 22))
    assert attribution_key(["7d_click", "1d_view"], "conversion") == attribution_key(
        ["1d_view", "7d_click"], "conversion"
    )


def test_account_today_uses_offset_when_zone_unknown():
    assert isinstance(account_today("Not/AZone", "5.5"), date)
