import pytest

from apps.api.location import normalize_delivery_location


def test_source_fields_normalized_without_changing_address():
    address = {
        "city": "  Chennai  ",
        "state": "Tamil   Nadu",
        "pincode": "600001",
        "country": "India",
        "full": "Original free text",
    }
    result = normalize_delivery_location(address)
    assert result["delivery_city"] == "CHENNAI"
    assert result["delivery_state"] == "TAMIL NADU"
    assert result["delivery_country"] == "INDIA"
    assert result["delivery_pincode"] == "600001"
    assert result["delivery_location_sources"] == {
        "city": "SOURCE",
        "state": "SOURCE",
        "country": "SOURCE",
        "pincode": "SOURCE",
    }
    assert address["city"] == "  Chennai  "


def test_no_guessing_from_full_address_or_pin():
    result = normalize_delivery_location({"full": "Chennai Tamil Nadu India 600001"})
    assert result["delivery_city"] is None
    assert result["delivery_pincode"] is None
    result = normalize_delivery_location({"pincode": 600001})
    assert result["delivery_country"] is None
    assert result["delivery_state"] is None
    assert result["delivery_location_sources"] == {"pincode": "SOURCE"}


@pytest.mark.parametrize("pin", [None, "", True, 600001.0, "060001", "60001", "6000012", "ABCDEF"])
def test_invalid_pin_stays_unknown(pin):
    assert normalize_delivery_location({"pincode": pin})["delivery_pincode"] is None


@pytest.mark.parametrize("address", [None, {}, {"city": "N/A", "state": [], "country": {}}])
def test_missing_location_not_an_order_error(address):
    result = normalize_delivery_location(address)
    assert result["delivery_location_sources"] == {}
    assert all(value is None for key, value in result.items() if key != "delivery_location_sources")
