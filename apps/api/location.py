"""Extract reporting fields without guessing missing address components."""

import html
import re


def clean_place(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    result = " ".join(html.unescape(value).split()).upper()
    if result in ("", "-", "N/A", "NA", "UNKNOWN", "NULL", "NONE"):
        return None
    return result


def normalize_delivery_location(address: dict | None) -> dict:
    address = address or {}
    result = {
        "delivery_city": clean_place(address.get("city")),
        "delivery_state": clean_place(address.get("state")),
        "delivery_country": clean_place(address.get("country")),
        "delivery_pincode": None,
    }
    pin = address.get("pincode")
    if isinstance(pin, (str, int)) and not isinstance(pin, bool):
        pin = str(pin).strip()
        if re.fullmatch(r"[1-9][0-9]{5}", pin):
            result["delivery_pincode"] = pin
    # Provenance is per field, allowing verified lookup-derived fields later.
    result["delivery_location_sources"] = {
        key.removeprefix("delivery_"): "SOURCE"
        for key, value in result.items()
        if value is not None
    }
    return result
