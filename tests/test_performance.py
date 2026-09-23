from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from apps.api.config import get_settings
from apps.api.main import app
from apps.api.performance import comparison_window, delta, period_values


def test_week_matches_completed_weekdays():
    window = comparison_window("week", date(2026, 9, 23))
    assert window["current_start"] == date(2026, 9, 21)
    assert window["current_end"] == date(2026, 9, 22)
    assert window["previous_start"] == date(2026, 9, 14)
    assert window["previous_end"] == date(2026, 9, 15)
    assert window["days"] == 2


@pytest.mark.parametrize(
    "period,today",
    [
        ("week", date(2026, 9, 21)),
        ("month", date(2026, 10, 1)),
    ],
)
def test_period_with_no_completed_days_is_explicit(period, today):
    window = comparison_window(period, today)
    assert window["days"] == 0
    assert window["current_end"] is None


def test_month_clamps_both_windows_to_shorter_month():
    window = comparison_window("month", date(2026, 3, 31))
    assert window["days"] == 28
    assert window["current_end"] == date(2026, 3, 28)
    assert window["previous_end"] == date(2026, 2, 28)


def test_leap_year_and_year_rollover():
    leap = comparison_window("month", date(2024, 3, 31))
    assert leap["days"] == 29
    january = comparison_window("month", date(2026, 1, 15))
    assert january["previous_start"] == date(2025, 12, 1)
    assert january["previous_end"] == date(2025, 12, 14)
    yesterday = comparison_window("yesterday", date(2026, 1, 1))
    assert yesterday["current_start"] == date(2025, 12, 31)
    assert yesterday["previous_start"] == date(2025, 12, 30)


def test_today_is_partial_and_not_same_hour():
    window = comparison_window("today", date(2026, 9, 23))
    assert window["partial"] is True
    assert window["previous_end"] == date(2026, 9, 22)
    assert delta(100, 200, comparable=False)["state"] == "unavailable"


def test_zero_missing_and_negative_changes():
    assert delta(100, 0)["state"] == "no_baseline"
    assert delta(0, 0)["percent"] == 0
    assert delta(None, 50)["state"] == "unavailable"
    assert delta(50, 100)["percent"] == Decimal("-50.00")
    assert delta(0, 100)["percent"] == Decimal("-100.00")


def report(missing=0, currency="INR", spend=100):
    return {
        "coverage": {"unsynced_days": missing},
        "context": {"account": {"currency": currency}},
        "business": {"revenue": 1000, "orders": 4, "new_customers": 2},
        "meta": {"spend": spend, "meta_roas": 2},
    }


def test_missing_meta_is_not_zero_and_zero_spend_is_valid():
    values = period_values(report(missing=1), 250)
    assert values["spend"] is None
    assert values["mer"] is None
    assert values["revenue"] == 1000
    zero = period_values(report(spend=0), 250)
    assert zero["spend"] == 0
    assert zero["mer"] is None
    assert zero["spend_per_new_customer"] == 0


def test_currency_mismatch_suppresses_cross_currency_ratios():
    values = period_values(report(currency="USD"), 250)
    assert values["spend"] == 100
    assert values["mer"] is None
    assert values["spend_per_new_customer"] is None
    assert values["meta_roas"] == 2


def test_ratios_use_orders_and_new_customer_denominators():
    values = period_values(report(), 250)
    assert values["aov"] == 250
    assert values["mer"] == 10
    assert values["spend_per_new_customer"] == 50
    assert values["repeat_revenue"] == 250


def test_api_auth_and_period_validation(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ADMIN_API_TOKEN", "comparison-test-only")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        assert client.get("/admin/performance").status_code == 401
        assert (
            client.get(
                "/admin/performance?period=invalid",
                headers={
                    "Authorization": "Bearer comparison-test-only",
                },
            ).status_code
            == 422
        )
    finally:
        get_settings.cache_clear()


def test_older_orders_keep_calculations_with_provisional_label():
    from apps.api.performance import compare_values, insight_messages

    current = period_values(report(), 250)
    previous = period_values(report(spend=200), 300)
    metrics = compare_values(current, previous, False, True, False)
    assert metrics["revenue"]["change"]["percent"] == 0
    assert metrics["mer"]["current"] == 10
    assert metrics["spend_per_new_customer"]["current"] == 50
    assert metrics["spend_per_new_customer"]["provisional"] is True
    assert metrics["spend"]["provisional"] is False
    assert metrics["spend"]["change"]["percent"] == -50
    assert any("provisional" in message for message in insight_messages(metrics, False))


def test_monthly_cac_uses_actual_new_customers_not_meta_purchases():
    from apps.api.performance import compare_values

    current = report(spend=Decimal("58377.12"))
    current["business"]["new_customers"] = 127
    current["meta"]["meta_purchases"] = 183
    previous = report(spend=Decimal("46754.44"))
    previous["business"]["new_customers"] = 158
    metrics = compare_values(
        period_values(current, 0),
        period_values(previous, 0),
        False,
        True,
        False,
    )
    assert metrics["spend_per_new_customer"]["current"] == Decimal("459.66")
    assert metrics["spend_per_new_customer"]["previous"] == Decimal("295.91")
    assert metrics["spend_per_new_customer"]["change"]["state"] == "compared"


def test_week_without_new_customers_has_undefined_cac():
    current = report(spend=Decimal("4067.49"))
    current["business"]["new_customers"] = 0
    current["meta"]["meta_purchases"] = 20
    assert period_values(current, 0)["spend_per_new_customer"] is None
