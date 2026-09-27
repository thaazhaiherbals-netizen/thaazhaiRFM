import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_order_processing import engine as engine
from test_order_processing import insert_raw, payload, rows

from apps.api import jobs, operations
from apps.api.config import get_settings
from apps.api.main import app

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_TESTS") != "1", reason="Needs disposable PostgreSQL"
)


@pytest.fixture
def client(engine, monkeypatch):
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE processing_jobs CASCADE"))
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-token-only")
    get_settings.cache_clear()
    monkeypatch.setattr(operations, "get_engine", lambda: engine)
    from apps.api import admin

    monkeypatch.setattr(admin, "get_engine", lambda: engine)
    with TestClient(app, headers={"Authorization": "Bearer test-token-only"}) as result:
        yield result
    get_settings.cache_clear()


def process_all(client, engine):
    assert client.post("/admin/jobs/process-pending").status_code == 202
    assert jobs.run_next_job(engine)


def test_catalogue_ids_match_aliases_without_matching_similar_products(client, engine):
    for name, phone, product in [
        ("mapped-a1", "9000000301", "Old aloe alias"), ("mapped-a2", "9000000301", "Old aloe alias"),
        ("mapped-b", "9000000301", "Old colour alias"),
        ("premium-1", "9000000302", "Aloe Gel Premium"), ("premium-2", "9000000302", "Aloe Gel Premium"),
        ("unmapped", "9000000303", "Aloe Gel unknown"),
    ]:
        add_product_order(engine, name, phone, [product])
    process_all(client, engine)
    with engine.begin() as connection:
        ids = {}
        for raw, canonical in [("Old aloe alias", "Test Aloe Gel"), ("Old colour alias", "Test Hair Colour"),
                               ("Aloe Gel Premium", "Test Aloe Gel Premium")]:
            product_id = connection.execute(text("INSERT INTO products (canonical_name) VALUES (:name) RETURNING id"), {"name": canonical}).scalar_one()
            ids[canonical] = str(product_id)
            connection.execute(text("UPDATE order_items SET product_id=:id, mapping_status='RESOLVED', mapping_error=NULL WHERE raw_product_name=:raw"), {"id": product_id, "raw": raw})
    a, b = ids["Test Aloe Gel"], ids["Test Hair Colour"]
    buyers = client.get(f"/customers?product_ids={a}").json()
    assert buyers["total"] == 1
    assert buyers["items"][0]["product_purchases"][0]["orders"] == 2
    assert buyers["items"][0]["product_purchases"][0]["product"] == "Test Aloe Gel"
    opportunity = client.get(f"/admin/product-opportunities?product_a={a}&product_b={b}").json()
    assert opportunity["total"] == 1
    assert "segment" in opportunity["items"][0]
    assert "follow_up_status" in opportunity["items"][0]
    assert client.get(f"/admin/product-opportunities?product_a={a}&product_b={b}&combo={a}").json()["total"] == 0
    options = client.get("/admin/product-options").json()
    assert {"id": a, "name": "Test Aloe Gel"} in options
    assert not any(product["name"] == "Aloe Gel unknown" for product in options)


def test_filtered_summaries_cover_every_page(client, engine):
    insert_raw(engine, payload("summary-one", total=500))
    insert_raw(engine, payload("summary-two", total=250))
    process_all(client, engine)
    page = client.get("/orders?limit=1").json()
    assert len(page["items"]) == 1
    assert page["summary"]["total"] == 2
    assert float(page["summary"]["revenue"]) == 750
    assert float(page["summary"]["average_order_value"]) == 375
    assert page["summary"]["customers"] == 1
    filtered = client.get("/orders?search=summary-one").json()
    assert float(filtered["summary"]["revenue"]) == 500
    empty = client.get("/orders?start_date=2099-01-01").json()
    assert empty["summary"]["total"] == 0
    assert float(empty["summary"]["revenue"]) == 0
    customers = client.get("/customers").json()
    assert customers["summary"]["repeat_customers"] == 1
    assert float(customers["summary"]["lifetime_value"]) == 750


def add_product_order(engine, name, phone, products):
    insert_raw(engine, payload(name, phone=phone, total=100 * len(products), products=[
        {"product": product, "variant": "100ml", "quantity": 3, "unit_price": 100}
        for product in products
    ]))


def test_product_repeat_filters_count_orders_not_units_or_lines(client, engine):
    add_product_order(engine, "repeat-a1", "9000000101", ["Aloe Gel", "Aloe Gel"])
    add_product_order(engine, "repeat-a2", "9000000101", ["Aloe Gel", "Shampoo"])
    add_product_order(engine, "repeat-a3", "9000000101", ["Shampoo"])
    add_product_order(engine, "single-a1", "9000000102", ["Aloe Gel", "Aloe Gel"])
    process_all(client, engine)
    page = client.get("/customers?product_search=ALOE&min_product_orders=2").json()
    assert page["total"] == 1
    assert page["items"][0]["normalized_phone"].endswith("9000000101")
    assert page["items"][0]["product_purchases"][0]["orders"] == 2
    assert client.get("/customers?product_search=aloe,shampoo&product_match=all").json()["total"] == 1
    assert client.get("/customers?product_search=aloe,missing&product_match=all").json()["total"] == 0
    assert client.get("/customers?product_search=aloe,missing&product_match=any").json()["total"] == 1
    assert client.get("/customers?product_search=aloe&min_product_orders=1").json()["total"] == 2
    assert client.get("/customers?product_search=aloe&min_product_orders=3").json()["total"] == 0


def test_combo_and_cross_sell_opportunities(client, engine):
    for suffix, phone, products in [
        ("separate-a", "9000000201", ["Aloe Gel"]), ("separate-b", "9000000201", ["Hair Colour"]),
        ("same-order", "9000000202", ["Aloe Gel", "Hair Colour"]),
        ("combo-a", "9000000203", ["Aloe Gel"]), ("combo-b", "9000000203", ["Hair Colour"]),
        ("combo-c", "9000000203", ["Aloe Hair Combo"]),
        ("only-a", "9000000204", ["Aloe Gel"]), ("dnc-a", "9000000205", ["Aloe Gel"]),
    ]:
        add_product_order(engine, suffix, phone, products)
    process_all(client, engine)
    dnc = client.get("/customers?search=9000000205").json()["items"][0]["id"]
    client.post(f"/admin/customers/{dnc}/follow-ups", json={"status": "DO_NOT_CONTACT", "contacted_by": "Test agent"})
    query = "/admin/product-opportunities?product_a=aloe%20gel&product_b=hair%20colour&combo=aloe%20hair%20combo"
    data = client.get(query).json()
    assert data["total"] == 1
    assert data["items"][0]["normalized_phone"].endswith("9000000201")
    assert data["items"][0]["a_orders"] == data["items"][0]["b_orders"] == 1
    cross = client.get(query + "&mode=cross_sell").json()
    assert cross["total"] == 1
    assert cross["items"][0]["normalized_phone"].endswith("9000000204")
    assert client.get(query + "&search=no-such-customer").json()["total"] == 0
    assert client.get("/admin/product-opportunities?product_a=aloe&product_b=aloe").status_code == 422
    assert all("id" in product and "name" in product for product in client.get("/admin/product-options").json())


def test_order_date_range_includes_boundaries_and_preserves_search(client, engine):
    for name, day in [("early", "April 2, 2026"), ("match-a", "April 3, 2026"),
                      ("match-b", "April 4, 2026"), ("late", "April 5, 2026")]:
        insert_raw(engine, payload(name, order_date=day))
    process_all(client, engine)
    query = "/orders?start_date=2026-04-03&end_date=2026-04-04&search=match&limit=1"
    first = client.get(query).json()
    second = client.get(query + "&offset=1").json()
    assert first["total"] == second["total"] == 2
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert client.get("/orders?start_date=2026-04-05&end_date=2026-04-03").status_code == 422
    assert client.get("/orders?start_date=2026-02-30").status_code == 422


def test_support_summary_counts_people_and_latest_schedule(client, engine):
    insert_raw(engine, payload("support"))
    process_all(client, engine)
    customer_id = client.get("/customers").json()["items"][0]["id"]
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO customer_follow_ups
                (customer_id, status, channel, contacted_by, sentiment, contacted_at, next_follow_up_at)
            SELECT :id, status, 'CALL', 'Test agent', sentiment,
                (((now() AT TIME ZONE 'Asia/Kolkata')::date + time '00:00')
                    AT TIME ZONE 'Asia/Kolkata') + seq * interval '1 minute',
                CASE WHEN seq = 3 THEN NULL ELSE now() END
            FROM (VALUES (1, 'CONTACTED', 'POSITIVE'), (2, 'CONTACTED', 'NEGATIVE'),
                (3, 'NO_ANSWER', 'NOT_RECORDED')) AS events(seq, status, sentiment)
        """), {"id": customer_id})
    result = client.get("/admin/support-summary").json()
    assert result["contacted"] == 1
    assert result["positive"] == result["negative"] == 1
    assert result["scheduled"] == 0  # Superseded schedules must not remain due.
    with engine.begin() as connection:
        connection.execute(text("""
            UPDATE customer_follow_ups SET next_follow_up_at = now()
            WHERE customer_id = :id AND status = 'NO_ANSWER'
        """), {"id": customer_id})
        connection.execute(text("""
            INSERT INTO customer_follow_ups
                (customer_id, status, channel, contacted_by, sentiment, contacted_at)
            VALUES (:id, 'CONTACTED', 'CALL', 'Test agent', 'POSITIVE',
                ((now() AT TIME ZONE 'Asia/Kolkata')::date::timestamp
                    AT TIME ZONE 'Asia/Kolkata') - interval '1 second')
        """), {"id": customer_id})
    result = client.get("/admin/support-summary").json()
    assert result["scheduled"] == 1
    assert result["positive"] == 1  # Yesterday in India must be excluded.


def test_dashboard_order_customer_lists_and_details(client, engine):
    insert_raw(engine, payload("one", total=500))
    insert_raw(engine, payload("two", total=250, phone="+91 98765 43210"))
    process_all(client, engine)
    dashboard = client.get("/admin/dashboard").json()
    assert dashboard["order_count"] == 2
    assert dashboard["customer_count"] == 1
    assert dashboard["repeat_customer_count"] == 1
    assert float(dashboard["revenue"]) == 750
    assert float(dashboard["average_order_value"]) == 375

    order_page = client.get("/orders?search=one&limit=1").json()
    assert order_page["total"] == 1
    order_id = order_page["items"][0]["id"]
    detail = client.get(f"/orders/{order_id}").json()
    assert detail["order"]["source_record_id"] == "one"
    assert len(detail["items"]) == 1
    assert client.get("/orders/00000000-0000-0000-0000-000000000000").status_code == 404

    customers = client.get("/customers?search=9876543210").json()
    assert customers["total"] == 1
    assert customers["items"][0]["order_count"] == 2
    customer_id = customers["items"][0]["id"]
    customer = client.get(f"/customers/{customer_id}").json()
    assert len(customer["orders"]) == 2
    assert client.get("/customers/00000000-0000-0000-0000-000000000000").status_code == 404


def test_date_correction_preserves_raw_and_retries(client, engine):
    data = payload("missing-date")
    data.pop("order_date")
    ingestion_id = insert_raw(engine, data)
    process_all(client, engine)
    assert (
        rows(engine, "SELECT status FROM raw_order_ingestion WHERE id=:id", id=ingestion_id)[0][
            "status"
        ]
        == "ERROR"
    )

    response = client.put(
        f"/admin/ingestion/{ingestion_id}/order-date",
        json={"order_date": "2026-08-25", "reason": "Confirmed in Hostinger export"},
    )
    assert response.status_code == 202
    assert jobs.run_next_job(engine)
    saved = rows(engine, "SELECT * FROM orders WHERE ingestion_id=:id", id=ingestion_id)[0]
    assert str(saved["order_date"]) == "2026-08-25"
    raw = rows(engine, "SELECT raw_payload FROM raw_order_ingestion WHERE id=:id", id=ingestion_id)[
        0
    ]["raw_payload"]
    assert "order_date" not in raw
    correction = rows(
        engine, "SELECT * FROM order_corrections WHERE ingestion_id=:id", id=ingestion_id
    )[0]
    assert correction["reason"] == "Confirmed in Hostinger export"


def test_correction_validation_and_conflict(client, engine):
    ingestion_id = insert_raw(engine, payload())
    assert (
        client.put(
            f"/admin/ingestion/{ingestion_id}/order-date",
            json={"order_date": "2026-08-25", "reason": "valid reason"},
        ).status_code
        == 409
    )
    assert (
        client.put(
            "/admin/ingestion/00000000-0000-0000-0000-000000000000/order-date",
            json={"order_date": "2026-08-25", "reason": "valid reason"},
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"/admin/ingestion/{ingestion_id}/order-date",
            json={"order_date": "2026-08-25", "reason": "x"},
        ).status_code
        == 422
    )


def test_product_search_and_business_sorting(client, engine):
    insert_raw(
        engine,
        payload(
            "small-order",
            total=250,
            customer_name="Lower Value Customer",
            phone="9000000001",
            order_date="March 1, 2026",
        ),
    )
    insert_raw(
        engine,
        payload(
            "large-order",
            total=900,
            customer_name="Higher Value Customer",
            phone="9000000002",
            order_date="May 1, 2026",
        ),
    )
    process_all(client, engine)

    orders = client.get("/orders?search=glow%20face&sort=order_value&direction=asc").json()
    assert orders["total"] == 2
    assert [float(row["order_value"]) for row in orders["items"]] == [250, 900]

    customers = client.get(
        "/customers?search=face%20wash&sort=lifetime_value&direction=desc"
    ).json()
    assert customers["total"] == 2
    assert customers["items"][0]["customer_name"] == "Higher Value Customer"
    assert client.get("/orders?sort=not-a-column").status_code == 422
    assert client.get("/customers?direction=sideways").status_code == 422

    annual = client.get("/admin/analytics?year=2026").json()
    assert annual["grain"] == "month"
    assert len(annual["periods"]) == 12
    assert float(annual["summary"]["revenue"]) == 1150
    assert annual["products"][0]["product_name"] == "Herbal Glow Face Wash"

    monthly = client.get("/admin/analytics?year=2026&month=3").json()
    assert monthly["grain"] == "day"
    assert len(monthly["periods"]) == 31
    assert monthly["summary"]["new_customers"] == 1

    quarter = client.get("/admin/analytics?year=2026&window=quarter").json()
    assert quarter["window"] == "quarter"
    assert len(quarter["periods"]) == 3

def test_customer_follow_up_history_latest_status_and_filter(client, engine):
    insert_raw(engine, payload("follow-up-customer", phone="9000000011"))
    process_all(client, engine)
    customer = client.get("/customers?search=9000000011").json()["items"][0]
    assert customer["follow_up_status"] == "NOT_CONTACTED"

    created = client.post(
        f"/admin/customers/{customer['id']}/follow-ups",
        json={
            "status": "CALLBACK",
            "channel": "CALL",
            "contacted_by": "Anita",
            "sentiment": "MIXED",
            "feedback_tags": ["HAS_CONCERNS", "PRICE_TOO_HIGH", "WANTS_OFFER"],
            "purchase_intent": "MEDIUM",
            "offer_interest": True,
            "expected_order_date": "2026-09-30",
            "notes": "Requested a call after work",
            "next_follow_up_at": "2026-09-23T12:30:00+05:30",
        },
    )
    assert created.status_code == 201
    assert created.json()["status"] == "CALLBACK"
    assert created.json()["purchase_intent"] == "MEDIUM"
    assert created.json()["offer_interest"] is True
    assert "PRICE_TOO_HIGH" in created.json()["feedback_tags"]

    listing = client.get(
        "/customers?follow_up_status=CALLBACK&sort=last_follow_up_at&direction=desc"
    ).json()
    assert listing["total"] == 1
    assert listing["items"][0]["last_follow_up_by"] == "Anita"

    detail = client.get(f"/customers/{customer['id']}").json()
    assert len(detail["follow_ups"]) == 1
    assert detail["follow_ups"][0]["notes"] == "Requested a call after work"
    assert detail["follow_ups"][0]["sentiment"] == "MIXED"
    assert client.get("/customers?sales_signal=OFFER_INTEREST").json()["total"] == 1
    assert client.get("/customers?sales_signal=PRICE_HIGH").json()["total"] == 1
    assert client.get("/customers?follow_up_status=NOT_CONTACTED").json()["total"] == 0

    missing = client.post(
        "/admin/customers/00000000-0000-0000-0000-000000000000/follow-ups",
        json={
            "status": "CONTACTED",
            "channel": "CALL",
            "contacted_by": "Anita",
        },
    )
    assert missing.status_code == 404

def test_customer_segments_and_tags(client, engine):
    insert_raw(
        engine,
        payload(
            "segment-new",
            total=900,
            phone="9000000021",
            order_date="September 15, 2026",
        ),
    )
    insert_raw(
        engine,
        payload(
            "segment-repeat-one",
            total=700,
            phone="9000000022",
            order_date="August 10, 2026",
        ),
    )
    insert_raw(
        engine,
        payload(
            "segment-repeat-two",
            total=700,
            phone="9000000022",
            order_date="September 10, 2026",
        ),
    )
    process_all(client, engine)

    settings = client.get("/admin/customer-segment-settings")
    assert settings.status_code == 200
    assert settings.json()["new_customer_days"] == 30
    invalid = client.put(
        "/admin/customer-segment-settings",
        json={
            "new_customer_days": 90,
            "active_customer_days": 90,
            "champion_recency_days": 60,
            "champion_min_orders": 3,
            "high_value_percentile": 0.75,
            "vip_value_percentile": 0.90,
        },
    )
    assert invalid.status_code == 422
    updated = client.put(
        "/admin/customer-segment-settings",
        json={
            "new_customer_days": 25,
            "active_customer_days": 90,
            "champion_recency_days": 60,
            "champion_min_orders": 3,
            "high_value_percentile": 0.75,
            "vip_value_percentile": 0.90,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["new_customer_days"] == 25

    summary = client.get("/admin/customer-segments")
    assert summary.status_code == 200
    body = summary.json()
    assert body["settings"]["new_customer_days"] == 25
    assert sum(item["customer_count"] for item in body["segments"]) == 2
    assert float(body["thresholds"]["high_value"]) > 0

    customers = client.get("/customers?segment=LOYAL_REPEAT").json()
    assert customers["total"] == 1
    repeat = customers["items"][0]
    assert repeat["order_count"] == 2
    assert repeat["segment"] == "LOYAL_REPEAT"
    assert "REPEAT_BUYER" in repeat["tags"]
    assert "HAIR_CARE" not in repeat["tags"]
    assert client.get("/customers?tag=REPEAT_BUYER").json()["total"] == 1
    assert client.get("/customers?tag=NOT_REAL").status_code == 422
    assert client.get("/customers?segment=NOT_REAL").status_code == 422

