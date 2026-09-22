import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_order_processing import engine as engine
from test_order_processing import insert_raw, payload, rows

from apps.api import admin, jobs
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
    monkeypatch.setattr(admin, "get_engine", lambda: engine)
    with TestClient(app, headers={"Authorization": "Bearer test-token-only"}) as client:
        yield client
    get_settings.cache_clear()


def test_auth_and_public_health(client, monkeypatch):
    assert client.get("/health", headers={"Authorization": ""}).status_code == 200
    assert client.get("/admin/jobs", headers={"Authorization": ""}).status_code == 401
    assert (
        client.post(
            "/admin/jobs/process-pending", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    monkeypatch.setenv("ADMIN_API_TOKEN", "")
    get_settings.cache_clear()
    assert client.get("/admin/jobs").status_code == 503


def test_job_is_queued_then_worker_processes_mixed_results(client, engine):
    good = insert_raw(engine, payload("good"))
    bad = insert_raw(engine, payload("bad", phone=""))
    response = client.post("/admin/jobs/process-pending")
    assert response.status_code == 202
    job = response.json()
    assert job["total_records"] == 2
    assert job["status"] == "QUEUED"
    assert not rows(engine, "SELECT * FROM orders")
    assert client.post("/admin/jobs/process-pending").status_code == 409
    assert jobs.run_next_job(engine, batch_size=1)
    result = client.get(f"/admin/jobs/{job['id']}").json()
    assert result["status"] == "COMPLETED"
    assert (result["processed_count"], result["success_count"], result["failed_count"]) == (2, 1, 1)
    assert client.get("/admin/errors").json()["total"] == 1
    assert client.get("/admin/ingestion?status=PROCESSED").json()["total"] == 1
    assert client.get("/admin/ingestion?limit=999").status_code == 422
    assert client.get(f"/admin/jobs/{job['id']}/items").json()["total"] == 2
    assert client.get("/admin/ingestion/summary").json()["PROCESSED"] == 1
    assert client.post(f"/admin/ingestion/{good}/retry").status_code == 409
    retry = client.post(f"/admin/ingestion/{bad}/retry")
    assert retry.status_code == 202
    jobs.run_next_job(engine)
    assert (
        rows(engine, "SELECT retry_count FROM raw_order_ingestion WHERE id=:id", id=bad)[0][
            "retry_count"
        ]
        == 1
    )


def test_job_snapshot_and_no_work_job(client, engine):
    job = client.post("/admin/jobs/process-pending").json()
    insert_raw(engine, payload())
    jobs.run_next_job(engine)
    result = client.get(f"/admin/jobs/{job['id']}").json()
    assert result["status"] == "COMPLETED"
    assert result["processed_count"] == 0
    assert not rows(engine, "SELECT * FROM orders")


def test_resume_after_crash_does_not_duplicate_committed_records(client, engine, monkeypatch):
    insert_raw(engine, payload("one"))
    insert_raw(engine, payload("two"))
    job = client.post("/admin/jobs/process-pending").json()
    original = jobs.process_single_order
    calls = 0

    def crash_on_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated worker restart")
        return original(*args, **kwargs)

    monkeypatch.setattr(jobs, "process_single_order", crash_on_second)
    with pytest.raises(RuntimeError):
        jobs.run_next_job(engine)
    assert client.get(f"/admin/jobs/{job['id']}").json()["processed_count"] == 1
    monkeypatch.setattr(jobs, "process_single_order", original)
    jobs.run_next_job(engine)
    assert len(rows(engine, "SELECT * FROM orders")) == 2
    result = client.get(f"/admin/jobs/{job['id']}").json()
    assert result["processed_count"] == result["success_count"] == 2


def test_order_and_job_progress_rollback_together(client, engine, monkeypatch):
    raw_id = insert_raw(engine, payload())
    job = client.post("/admin/jobs/process-pending").json()
    original = jobs.process_single_order

    def crash_after_processing(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("crash before job progress")

    monkeypatch.setattr(jobs, "process_single_order", crash_after_processing)
    with pytest.raises(RuntimeError):
        jobs.run_next_job(engine)
    assert not rows(engine, "SELECT * FROM orders")
    assert (
        rows(engine, "SELECT status FROM raw_order_ingestion WHERE id=:id", id=raw_id)[0]["status"]
        == "NEW"
    )
    assert client.get(f"/admin/jobs/{job['id']}").json()["processed_count"] == 0
    monkeypatch.setattr(jobs, "process_single_order", original)
    jobs.run_next_job(engine)
    assert len(rows(engine, "SELECT * FROM orders")) == 1


def test_second_worker_cannot_claim_job(client, engine):
    client.post("/admin/jobs/process-pending")
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": jobs.WORKER_LOCK})
        connection.commit()
        try:
            assert jobs.run_next_job(engine) is False
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": jobs.WORKER_LOCK})
            connection.commit()


def test_alias_fix_and_resolve_job_preserve_sale(client, engine):
    data = payload()
    data["products"][0]["variant"] = "new label"
    insert_raw(engine, data)
    client.post("/admin/jobs/process-pending")
    jobs.run_next_job(engine)
    assert client.get("/admin/unmapped-products").json()["total"] == 1
    # Unresolved work is reported as failed in a resolve job, not silently successful.
    unresolved = client.post("/admin/jobs/resolve-mappings").json()
    jobs.run_next_job(engine)
    assert client.get(f"/admin/jobs/{unresolved['id']}").json()["failed_count"] == 1
    catalog = client.get("/admin/products").json()["items"]
    face = next(row for row in catalog if row["canonical_name"] == "Herbal Glow Face Wash")
    mapping = {
        "alias_name": "HERBAL GLOW FACE WASH",
        "alias_variant": "new label",
        "product_id": face["product_id"],
        "variant_id": face["variant_id"],
    }
    alias = client.post("/admin/product-aliases", json=mapping)
    assert alias.status_code == 201
    assert client.post("/admin/product-aliases", json=mapping).status_code == 409
    assert (
        client.put(f"/admin/product-aliases/{alias.json()['id']}", json=mapping).status_code == 200
    )
    resolve = client.post("/admin/jobs/resolve-mappings").json()
    jobs.run_next_job(engine)
    assert client.get(f"/admin/jobs/{resolve['id']}").json()["success_count"] == 1
    assert client.get("/admin/unmapped-products").json()["total"] == 0
    assert len(rows(engine, "SELECT * FROM orders")) == 1
    assert rows(engine, "SELECT order_value FROM orders")[0]["order_value"] == 500
    assert client.delete(f"/admin/product-aliases/{alias.json()['id']}").status_code == 204


def test_alias_rejects_mismatched_variant(client):
    catalog = client.get("/admin/products").json()["items"]
    first = catalog[0]
    other = next(row for row in catalog if row["product_id"] != first["product_id"])
    response = client.post(
        "/admin/product-aliases",
        json={
            "alias_name": "wrong",
            "product_id": first["product_id"],
            "variant_id": other["variant_id"],
        },
    )
    assert response.status_code == 422
