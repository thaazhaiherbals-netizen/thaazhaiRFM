from decimal import Decimal

import pytest

from apps.api.normalization import OrderValidationError, money, normalize_phone, normalize_text


@pytest.mark.parametrize(
    "phone",
    [
        "9876543210",
        "919876543210",
        "+91 98765 43210",
        "+91-98765-43210",
    ],
)
def test_phone_formats(phone):
    assert normalize_phone(phone) == "+919876543210"


@pytest.mark.parametrize("phone", [None, "", "123", "9876543210 ext 1", "abcdefghij"])
def test_invalid_phone(phone):
    with pytest.raises(OrderValidationError):
        normalize_phone(phone)


def test_alias_text():
    assert normalize_text("  Rose &amp;  VETIVER ") == "rose & vetiver"
    assert normalize_text(None) == normalize_text(" ")


@pytest.mark.parametrize("value", [True, "-1", "NaN", "Infinity", "1.234", "10000000000"])
def test_invalid_money(value):
    with pytest.raises(OrderValidationError):
        money(value, "total")


def test_decimal_money():
    assert money("450.10", "total") == Decimal("450.10")
