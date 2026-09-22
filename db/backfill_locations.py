"""Populate untouched location reporting fields from existing orders.address."""

import json

from sqlalchemy import Engine, text

from apps.api.config import get_settings
from apps.api.db import get_engine
from apps.api.location import normalize_delivery_location


def backfill_locations(engine: Engine) -> int:
    count = 0
    with engine.begin() as connection:
        orders = (
            connection.execute(
                text("""
            SELECT id, address FROM orders
            WHERE delivery_location_sources = '{}'::jsonb
                AND delivery_city IS NULL AND delivery_state IS NULL
                AND delivery_country IS NULL AND delivery_pincode IS NULL
            ORDER BY id FOR UPDATE
        """)
            )
            .mappings()
            .all()
        )
        for order in orders:
            address = order["address"]
            if address is not None and not isinstance(address, dict):
                continue
            values = normalize_delivery_location(address)
            if not values["delivery_location_sources"]:
                continue
            connection.execute(
                text("""
                UPDATE orders SET delivery_city = :delivery_city,
                    delivery_state = :delivery_state, delivery_country = :delivery_country,
                    delivery_pincode = :delivery_pincode,
                    delivery_location_sources = CAST(:delivery_location_sources AS JSONB)
                WHERE id = :id
            """),
                {
                    **values,
                    "id": order["id"],
                    "delivery_location_sources": json.dumps(values["delivery_location_sources"]),
                },
            )
            count += 1
    return count


if __name__ == "__main__":
    if get_settings().app_env != "development":
        raise SystemExit("This manual command is limited to local development")
    print(f"Updated location fields on {backfill_locations(get_engine())} local orders.")
