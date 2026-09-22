"""Real PostgreSQL integration tests; never run against development business data."""

import json
import os
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from apps.api import order_processing
from apps.api.config import get_settings
from apps.api.db import get_engine
from apps.api.order_processing import process_single_order
from db.migrate import run

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_TESTS") != "1", reason="Needs disposable PostgreSQL"
)


@pytest.fixture
def engine():
    get_settings.cache_clear()
    get_engine.cache_clear()
    db = get_engine()
    assert get_settings().app_env == "test"
    assert db.url.database.endswith("_check"), "Refusing non-test database"
    run(seed=True)
    with db.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE order_items, orders, customers, raw_order_ingestion, "
                "product_aliases, product_variants, products CASCADE"
            )
        )
        from pathlib import Path

        for path in sorted(Path("db/seeds").glob("*.sql")):
            with connection.connection.driver_connection.cursor() as cursor:
                cursor.execute(path.read_text(encoding="utf-8"))
    yield db
    db.dispose()


def payload(order_id="test-1", **updates):
    data = {
        "order_id": order_id,
        "order_date": "April 3, 2026",
        "customer_name": "Synthetic Customer",
        "phone": "9876543210",
        "total": 500,
        "products": [
            {
                "product": "HERBAL GLOW FACE WASH",
                "variant": "100ml",
                "quantity": 2,
                "unit_price": 250,
            },
        ],
    }
    data.update(updates)
    return data


def insert_raw(engine, data, status="NEW"):
    ingestion_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO raw_order_ingestion
                (id, source_system, source_record_id, raw_payload, status)
            VALUES (:id, 'HOSTINGER', :source_id, CAST(:payload AS JSONB), :status)
        """),
            {
                "id": ingestion_id,
                "source_id": data["order_id"],
                "payload": json.dumps(data),
                "status": status,
            },
        )
    return ingestion_id


def rows(engine, sql, **params):
    with engine.connect() as connection:
        return connection.execute(text(sql), params).mappings().all()


def test_new_customer_valid_order_and_raw_preserved(engine):
    data = payload()
    raw_id = insert_raw(engine, data)
    result = process_single_order(engine, raw_id)
    assert result.status == "PROCESSED"
    assert rows(engine, "SELECT * FROM customers")[0]["normalized_phone"] == "+919876543210"
    assert rows(engine, "SELECT * FROM order_items")[0]["line_total"] == Decimal("500.00")
    raw = rows(engine, "SELECT * FROM raw_order_ingestion")[0]
    assert raw["raw_payload"] == data
    assert raw["processed_at"] is not None
    assert raw["processing_started_at"] is not None


def test_existing_customer_and_out_of_order_dates(engine):
    for index, day in enumerate(["April 3, 2026", "May 1, 2026", "March 2, 2026"]):
        raw_id = insert_raw(engine, payload(str(index), order_date=day, phone="+91 98765 43210"))
        assert process_single_order(engine, raw_id).status == "PROCESSED"
    customers = rows(engine, "SELECT * FROM customers")
    assert len(customers) == 1
    assert customers[0]["first_order_date"] == date(2026, 3, 2)
    assert customers[0]["last_order_date"] == date(2026, 5, 1)
    assert len(rows(engine, "SELECT * FROM orders")) == 3


def test_multiple_products_and_shampoo_100(engine):
    data = payload()
    data["products"].append(
        {
            "product": "Thaazhai Herbal Conditioning Shampoo",
            "variant": "100",
            "quantity": 1,
            "unit_price": "300.10",
        }
    )
    result = process_single_order(engine, insert_raw(engine, data))
    assert result.status == "PROCESSED"
    items = rows(
        engine,
        """
        SELECT i.*, v.variant_name FROM order_items i
        JOIN product_variants v ON v.id = i.variant_id
    """,
    )
    assert len(items) == 2
    shampoo = next(i for i in items if i["raw_variant_name"] == "100")
    assert shampoo["variant_name"] == "100 ml"
    assert shampoo["unit_price"] == Decimal("300.10")


def test_unknown_alias_preserves_sale_and_pending_item(engine):
    data = payload()
    data["products"].append(
        {
            "product": "Not mapped",
            "variant": None,
            "quantity": 1,
            "unit_price": 10,
        }
    )
    raw_id = insert_raw(engine, data)
    result = process_single_order(engine, raw_id)
    assert result.status == "PROCESSED"
    assert result.pending_items == 1
    assert len(rows(engine, "SELECT * FROM customers")) == 1
    assert len(rows(engine, "SELECT * FROM orders")) == 1
    assert len(rows(engine, "SELECT * FROM order_items")) == 2
    pending = rows(engine, "SELECT * FROM order_items WHERE mapping_status = 'PENDING'")[0]
    assert pending["product_id"] is None
    assert pending["line_total"] == Decimal("10.00")
    assert pending["raw_product_name"] == "Not mapped"
    assert "Unmapped product" in pending["mapping_error"]
    assert rows(engine, "SELECT sum(order_value) AS revenue FROM orders")[0]["revenue"] == 500
    assert rows(engine, "SELECT raw_payload FROM raw_order_ingestion")[0]["raw_payload"] == data


def test_duplicate_processing_does_not_duplicate_order(engine):
    raw_id = insert_raw(engine, payload())
    first = process_single_order(engine, raw_id)
    second = process_single_order(engine, raw_id)
    assert first.order_id == second.order_id
    assert len(rows(engine, "SELECT * FROM orders")) == 1
    assert len(rows(engine, "SELECT * FROM customers")) == 1
    assert len(rows(engine, "SELECT * FROM order_items")) == 1


def test_null_variant_mapping(engine):
    data = payload(
        products=[
            {
                "product": "Herbal Hair Colour + Aloe Vera Combo",
                "variant": None,
                "quantity": 1,
                "unit_price": 500,
            }
        ]
    )
    assert process_single_order(engine, insert_raw(engine, data)).status == "PROCESSED"
    assert (
        rows(
            engine,
            """
        SELECT variant_name FROM product_variants
        WHERE id = (SELECT variant_id FROM order_items)
    """,
        )[0]["variant_name"]
        == "Kit"
    )


def test_reprocess_after_correcting_mapping_preserves_sale(engine):
    data = payload()
    data["products"][0]["variant"] = "new label"
    raw_id = insert_raw(engine, data)
    first = process_single_order(engine, raw_id)
    assert first.status == "PROCESSED"
    assert first.pending_items == 1
    before = rows(engine, "SELECT * FROM order_items")[0]
    with engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO product_aliases
                (product_id, variant_id, source_system, alias_name, alias_variant, normalized_alias)
            SELECT product_id, variant_id, source_system, alias_name, 'new label', normalized_alias
            FROM product_aliases WHERE alias_name = 'HERBAL GLOW FACE WASH'
        """)
        )
    result = process_single_order(engine, raw_id)
    assert result.order_id == first.order_id
    assert result.pending_items == 0
    after = rows(engine, "SELECT * FROM order_items")[0]
    assert before["id"] == after["id"]
    assert before["line_total"] == after["line_total"]
    assert after["product_id"] is not None
    assert len(rows(engine, "SELECT * FROM orders")) == 1


def test_failure_after_all_inserts_rolls_back_customer_dates_and_items(engine, monkeypatch):
    first = insert_raw(engine, payload())
    assert process_single_order(engine, first).status == "PROCESSED"
    original = order_processing.create_normalized_order

    def injected_failure(connection, raw):
        original(connection, raw)
        raise RuntimeError("Synthetic secret that must not be stored")

    monkeypatch.setattr(order_processing, "create_normalized_order", injected_failure)
    second = insert_raw(engine, payload("second", order_date="June 1, 2026"))
    result = process_single_order(engine, second)
    assert result.status == "ERROR"
    assert "Synthetic secret" not in result.error
    assert len(rows(engine, "SELECT * FROM orders")) == 1
    assert len(rows(engine, "SELECT * FROM order_items")) == 1
    assert rows(engine, "SELECT last_order_date FROM customers")[0]["last_order_date"] == date(
        2026, 4, 3
    )


def test_locked_record_is_not_processed_by_another_connection(engine):
    raw_id = insert_raw(engine, payload())
    with engine.begin() as connection:
        connection.execute(
            text("SELECT id FROM raw_order_ingestion WHERE id = :id FOR UPDATE"), {"id": raw_id}
        )
        assert process_single_order(engine, raw_id).status == "UNAVAILABLE"
    assert not rows(engine, "SELECT * FROM orders")
    assert process_single_order(engine, raw_id).status == "PROCESSED"


@pytest.mark.parametrize(
    "updates",
    [
        {"phone": ""},
        {"order_date": "not a date"},
        {"products": []},
        {"total": -1},
        {
            "products": [
                {
                    "product": "HERBAL GLOW FACE WASH",
                    "variant": "100ml",
                    "quantity": True,
                    "unit_price": 250,
                }
            ]
        },
    ],
)
def test_invalid_payload_is_error_without_partial_data(engine, updates):
    raw_id = insert_raw(engine, payload(**updates))
    assert process_single_order(engine, raw_id).status == "ERROR"
    assert not rows(engine, "SELECT * FROM customers")


def test_ambiguous_mapping_rejected(engine):
    with engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO product_aliases
                (product_id, variant_id, source_system, alias_name, alias_variant, normalized_alias)
            SELECT product_id, variant_id, source_system, alias_name,
                   alias_variant, normalized_alias
            FROM product_aliases WHERE alias_name = 'HERBAL GLOW FACE WASH'
        """)
        )
    result = process_single_order(engine, insert_raw(engine, payload()))
    assert result.status == "PROCESSED"
    assert result.pending_items == 1
    assert "Ambiguous" in rows(engine, "SELECT mapping_error FROM order_items")[0]["mapping_error"]


def test_inactive_variant_rejected(engine):
    with engine.begin() as connection:
        connection.execute(text("UPDATE product_variants SET active = FALSE"))
    result = process_single_order(engine, insert_raw(engine, payload()))
    assert result.status == "PROCESSED"
    assert result.pending_items == 1
    assert "Inactive" in rows(engine, "SELECT mapping_error FROM order_items")[0]["mapping_error"]


def test_retry_error_after_transient_failure(engine, monkeypatch):
    raw_id = insert_raw(engine, payload())
    original = order_processing.create_normalized_order

    def fail(connection, raw):
        original(connection, raw)
        raise RuntimeError("simulated transient failure")

    monkeypatch.setattr(order_processing, "create_normalized_order", fail)
    assert process_single_order(engine, raw_id).status == "ERROR"
    assert not rows(engine, "SELECT * FROM customers")
    assert not rows(engine, "SELECT * FROM orders")
    monkeypatch.setattr(order_processing, "create_normalized_order", original)
    assert process_single_order(engine, raw_id).status == "SKIPPED"
    assert process_single_order(engine, raw_id, retry_error=True).status == "PROCESSED"
    raw = rows(engine, "SELECT * FROM raw_order_ingestion")[0]
    assert raw["retry_count"] == 1
    assert raw["error_message"] is None


def test_delivery_locations_preserve_history_and_unknown_sales(engine):
    from db.backfill_locations import backfill_locations

    original = {"full": "Original address", "city": " Chennai ", "pincode": "600001"}
    first = insert_raw(engine, payload("loc-1", address=original))
    assert process_single_order(engine, first).status == "PROCESSED"
    second = insert_raw(engine, payload("loc-2", address={"city": "Madurai", "pincode": "625001"}))
    assert process_single_order(engine, second).status == "PROCESSED"
    third = insert_raw(engine, payload("loc-3", address={"pincode": "bad"}))
    assert process_single_order(engine, third).status == "PROCESSED"
    saved = rows(engine, "SELECT * FROM orders ORDER BY source_record_id")
    assert saved[0]["address"] == original
    assert saved[0]["delivery_city"] == "CHENNAI"
    assert saved[0]["delivery_state"] is None
    assert saved[0]["delivery_country"] is None
    assert saved[1]["delivery_city"] == "MADURAI"
    assert saved[2]["delivery_pincode"] is None
    assert len(rows(engine, "SELECT * FROM customers")) == 1
    assert rows(engine, "SELECT sum(order_value) AS revenue FROM orders")[0]["revenue"] == 1500
    assert backfill_locations(engine) == 0
    # Simulate a pre-migration order with untouched reporting fields.
    with engine.begin() as connection:
        connection.execute(
            text("""
            UPDATE orders SET delivery_city = NULL, delivery_pincode = NULL,
                delivery_location_sources = '{}'::jsonb WHERE source_record_id = 'loc-1'
        """)
        )
    assert backfill_locations(engine) == 1
    assert backfill_locations(engine) == 0
    restored = rows(engine, "SELECT * FROM orders WHERE source_record_id = 'loc-1'")[0]
    assert restored["address"] == original
    assert restored["delivery_city"] == "CHENNAI"
    assert restored["delivery_location_sources"] == {"city": "SOURCE", "pincode": "SOURCE"}
    assert restored["order_value"] == saved[0]["order_value"]
    assert (
        rows(engine, "SELECT raw_payload FROM raw_order_ingestion WHERE id = :id", id=first)[0][
            "raw_payload"
        ]["address"]
        == original
    )
