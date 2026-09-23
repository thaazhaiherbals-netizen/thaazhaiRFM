import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from apps.api.integrations.meta.parser import (
    MetaParseError,
    action_totals,
    parse_insight_row,
    to_decimal,
    to_int,
)

FIXTURES = Path(__file__).parent / "fixtures" / "meta"


def rows(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["data"]


def test_numbers_are_decimal_not_float():
    assert to_decimal("1250.50") == Decimal("1250.50")
    assert to_decimal(0.1) == Decimal("0.1")
    assert to_decimal(None) is None
    assert to_decimal("") is None
    assert to_int("40000") == 40000
    with pytest.raises(MetaParseError):
        to_int("1.5")
    with pytest.raises(MetaParseError):
        to_decimal("NaN")
    with pytest.raises(MetaParseError):
        to_decimal("abc")


def test_overlapping_action_types_are_not_double_counted():
    parsed = parse_insight_row(rows("insights_page_1.json")[0])
    assert parsed.reporting_date == date(2026, 9, 1)
    assert parsed.spend == Decimal("1250.50")
    assert parsed.link_clicks == 600
    assert parsed.outbound_clicks == 580
    assert parsed.landing_page_views == 450
    assert parsed.add_to_cart == Decimal(40)
    assert parsed.checkouts_initiated == Decimal(20)
    assert parsed.purchases == Decimal(8)
    assert parsed.purchase_value == Decimal("4800.00")
    assert parsed.currency == "INR"


def test_unknown_actions_are_kept_raw_and_flagged():
    parsed = parse_insight_row(rows("insights_page_1.json")[0])
    assert parsed.unclassified_action_types == ["post_engagement"]
    assert any(a["action_type"] == "post_engagement" for a in parsed.actions)


def test_absent_fields_default_safely():
    parsed = parse_insight_row(rows("insights_page_1.json")[1])
    assert parsed.reach is None
    assert parsed.link_clicks == 0
    assert parsed.purchases == 0
    assert parsed.actions == []
    assert parsed.spend == Decimal("0.99")


def test_fallback_action_type_is_used_when_preferred_absent():
    parsed = parse_insight_row(rows("insights_page_2.json")[0])
    assert parsed.purchases == Decimal(5)
    assert parsed.purchase_value == Decimal("3000.00")
    assert parsed.leads == Decimal(2)


@pytest.mark.parametrize(
    "change",
    [
        {"ad_id": None},
        {"date_start": "2026-09-01", "date_stop": "2026-09-07"},
        {"date_start": "yesterday"},
        {"actions": "not-a-list"},
        {"actions": [{"value": "3"}]},
    ],
)
def test_malformed_rows_fail_safely(change):
    row = {**rows("insights_page_2.json")[0], **change}
    with pytest.raises(MetaParseError):
        parse_insight_row(row)


def test_duplicate_action_entries_are_summed_per_type():
    totals = action_totals(
        [{"action_type": "lead", "value": "1"}, {"action_type": "lead", "value": "2"}]
    )
    assert totals == {"lead": Decimal(3)}


def test_live_account_checkout_spelling_is_recognised():
    row = {**rows("insights_page_2.json")[0], "actions": [
        {"action_type": "initiate_checkout", "value": "6"},
        {"action_type": "offsite_conversion.fb_pixel_initiate_checkout", "value": "6"},
    ]}
    parsed = parse_insight_row(row)
    assert parsed.checkouts_initiated == Decimal(6)
    assert parsed.unclassified_action_types == []
