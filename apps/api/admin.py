"""Authenticated operational routes. Swagger documents request and response shapes."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from apps.api.auth import require_admin
from apps.api.db import get_engine
from apps.api.jobs import JobConflict, RecordNotRetryable, enqueue_job
from apps.api.normalization import normalize_text

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)], tags=["Admin"])
Status = Literal["NEW", "PROCESSING", "PROCESSED", "ERROR"]


class Page(BaseModel):
    items: list[dict]
    total: int


class Job(BaseModel):
    id: UUID
    job_type: str
    status: str
    total_records: int
    processed_count: int
    success_count: int
    failed_count: int
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime


class AliasInput(BaseModel):
    source_system: Literal["HOSTINGER"] = "HOSTINGER"
    alias_name: str = Field(min_length=1, max_length=255)
    alias_variant: str | None = Field(default=None, max_length=150)
    product_id: UUID
    variant_id: UUID | None = None


def paged(sql: str, params: dict, limit: int, offset: int) -> Page:
    with get_engine().connect() as connection:
        count = connection.execute(text(f"SELECT count(*) FROM ({sql}) q"), params).scalar_one()
        items = (
            connection.execute(
                text(sql + " LIMIT :limit OFFSET :offset"),
                {**params, "limit": limit, "offset": offset},
            )
            .mappings()
            .all()
        )
        return Page(items=[dict(row) for row in items], total=count)


@router.get("/ingestion/summary")
def summary() -> dict:
    with get_engine().connect() as connection:
        counts = {key: 0 for key in ("NEW", "PROCESSING", "PROCESSED", "ERROR")}
        counts.update(
            dict(
                connection.execute(
                    text("SELECT status, count(*) FROM raw_order_ingestion GROUP BY status")
                ).all()
            )
        )
        counts["pending_mapping_items"] = connection.execute(
            text("SELECT count(*) FROM order_items WHERE mapping_status = 'PENDING'")
        ).scalar_one()
        return counts


@router.get("/ingestion", response_model=Page)
def ingestion(
    status: Status | None = None,
    source_system: str | None = Query(None, max_length=30),
    sort: Literal[
        "ingested_at", "processed_at", "retry_count", "status", "source_record_id"
    ] = "ingested_at",
    direction: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Page:
    order_by = {
        "ingested_at": "ingested_at",
        "processed_at": "processed_at",
        "retry_count": "retry_count",
        "status": "status",
        "source_record_id": "source_record_id",
    }[sort]
    sql = f"""
        SELECT id, source_record_id, source_system, status, retry_count, ingested_at,
            processing_started_at, processed_at, error_message
        FROM raw_order_ingestion
        WHERE (CAST(:status AS TEXT) IS NULL OR status = :status)
            AND (CAST(:source AS TEXT) IS NULL OR source_system = :source)
        ORDER BY {order_by} {direction.upper()} NULLS LAST, id
    """
    return paged(
        sql,
        {"status": status, "source": source_system},
        limit,
        offset,
    )


@router.get("/errors", response_model=Page)
def errors(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> Page:
    return ingestion(status="ERROR", source_system=None, limit=limit, offset=offset)


def create_job(kind: str, ingestion_id: UUID | None = None) -> dict:
    try:
        return enqueue_job(get_engine(), kind, ingestion_id)
    except (JobConflict, RecordNotRetryable) as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/jobs/process-pending", response_model=Job, status_code=202)
def process_pending() -> dict:
    return create_job("PROCESS_PENDING")


@router.post("/jobs/retry-errors", response_model=Job, status_code=202)
def retry_errors() -> dict:
    return create_job("RETRY_ERRORS")


@router.post("/jobs/resolve-mappings", response_model=Job, status_code=202)
def resolve_mappings() -> dict:
    return create_job("RESOLVE_MAPPINGS")


@router.post("/ingestion/{ingestion_id}/retry", response_model=Job, status_code=202)
def retry_one(ingestion_id: UUID) -> dict:
    return create_job("RETRY_ONE", ingestion_id)


@router.get("/jobs", response_model=Page)
def jobs(
    sort: Literal[
        "created_at", "total_records", "processed_count", "success_count",
        "failed_count", "status"
    ] = "created_at",
    direction: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Page:
    order_by = {
        "created_at": "created_at",
        "total_records": "total_records",
        "processed_count": "processed_count",
        "success_count": "success_count",
        "failed_count": "failed_count",
        "status": "status",
    }[sort]
    sql = f"SELECT * FROM processing_jobs ORDER BY {order_by} {direction.upper()}, id"
    return paged(sql, {}, limit, offset)


@router.get("/jobs/{job_id}", response_model=Job)
def job_detail(job_id: UUID) -> dict:
    with get_engine().connect() as connection:
        result = (
            connection.execute(text("SELECT * FROM processing_jobs WHERE id = :id"), {"id": job_id})
            .mappings()
            .one_or_none()
        )
        if result is None:
            raise HTTPException(404, "Job not found")
        return dict(result)


@router.get("/jobs/{job_id}/items", response_model=Page)
def job_items(
    job_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Page:
    job_detail(job_id)
    return paged(
        """
        SELECT * FROM processing_job_items WHERE job_id = :id ORDER BY ingestion_id
    """,
        {"id": job_id},
        limit,
        offset,
    )


@router.get("/unmapped-products", response_model=Page)
def unmapped(
    sort: Literal[
        "affected_orders", "affected_items", "item_revenue", "product_name"
    ] = "affected_orders",
    direction: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Page:
    order_by = {
        "affected_orders": "affected_orders",
        "affected_items": "affected_items",
        "item_revenue": "item_revenue",
        "product_name": "i.raw_product_name",
    }[sort]
    sql = f"""
        SELECT o.source_system, i.raw_product_name, i.raw_variant_name,
            count(*) AS affected_items, count(DISTINCT o.id) AS affected_orders,
            sum(i.line_total) AS item_revenue, i.mapping_error
        FROM order_items i JOIN orders o ON o.id = i.order_id
        WHERE i.mapping_status = 'PENDING'
        GROUP BY o.source_system, i.raw_product_name, i.raw_variant_name, i.mapping_error
        ORDER BY {order_by} {direction.upper()}, o.source_system,
            i.raw_product_name, i.raw_variant_name
    """
    return paged(sql, {}, limit, offset)


@router.get("/products", response_model=Page)
def products(limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0)) -> Page:
    return paged(
        """
        SELECT p.id AS product_id, p.canonical_name, v.id AS variant_id, v.variant_name
        FROM products p LEFT JOIN product_variants v ON v.product_id = p.id AND v.active
        WHERE p.active ORDER BY p.canonical_name, v.variant_name, p.id, v.id
    """,
        {},
        limit,
        offset,
    )


@router.get("/product-aliases", response_model=Page)
def aliases(limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0)) -> Page:
    return paged(
        "SELECT * FROM product_aliases ORDER BY source_system, alias_name, id", {}, limit, offset
    )


def save_alias(data: AliasInput, alias_id: UUID | None = None) -> dict:
    normalized = normalize_text(data.alias_name)
    if not normalized:
        raise HTTPException(422, "Alias name cannot be blank")
    with get_engine().begin() as connection:
        # Serialize alias writes because legacy aliases have no unique normalized key.
        connection.execute(text("SELECT pg_advisory_xact_lock(748192042)"))
        valid = connection.execute(
            text("""
            SELECT id FROM products WHERE id = :id AND active
        """),
            {"id": data.product_id},
        ).scalar_one_or_none()
        if not valid:
            raise HTTPException(422, "Select an active product")
        if data.variant_id:
            valid = connection.execute(
                text("""
                SELECT id FROM product_variants
                WHERE id = :id AND product_id = :product AND active
            """),
                {"id": data.variant_id, "product": data.product_id},
            ).scalar_one_or_none()
            if not valid:
                raise HTTPException(
                    422, "Variant must be active and belong to the selected product"
                )
        if (
            alias_id
            and not connection.execute(
                text("SELECT id FROM product_aliases WHERE id = :id FOR UPDATE"), {"id": alias_id}
            ).scalar_one_or_none()
        ):
            raise HTTPException(404, "Alias not found")
        existing = (
            connection.execute(
                text("""
            SELECT id, alias_name, alias_variant FROM product_aliases
            WHERE source_system = :source AND active
        """),
                {"source": data.source_system},
            )
            .mappings()
            .all()
        )
        for row in existing:
            if (
                row["id"] != alias_id
                and normalize_text(row["alias_name"]) == normalized
                and (normalize_text(row["alias_variant"]) == normalize_text(data.alias_variant))
            ):
                raise HTTPException(409, "An active alias already exists; edit it instead")
        params = {**data.model_dump(), "normalized": normalized, "id": alias_id}
        if alias_id:
            sql = """
                UPDATE product_aliases SET product_id = :product_id, variant_id = :variant_id,
                    source_system = :source_system, alias_name = :alias_name,
                    alias_variant = :alias_variant, normalized_alias = :normalized, active = TRUE
                WHERE id = :id RETURNING *
            """
        else:
            sql = """
                INSERT INTO product_aliases
                    (product_id, variant_id, source_system, alias_name,
                     alias_variant, normalized_alias)
                VALUES (:product_id, :variant_id, :source_system, :alias_name,
                        :alias_variant, :normalized) RETURNING *
            """
        return dict(connection.execute(text(sql), params).mappings().one())


@router.post("/product-aliases", status_code=201)
def add_alias(data: AliasInput) -> dict:
    return save_alias(data)


@router.put("/product-aliases/{alias_id}")
def edit_alias(alias_id: UUID, data: AliasInput) -> dict:
    return save_alias(data, alias_id)


@router.delete("/product-aliases/{alias_id}", status_code=204)
def deactivate_alias(alias_id: UUID) -> None:
    with get_engine().begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(748192042)"))
        updated = connection.execute(
            text("UPDATE product_aliases SET active = FALSE WHERE id = :id RETURNING id"),
            {"id": alias_id},
        ).scalar_one_or_none()
        if updated is None:
            raise HTTPException(404, "Alias not found")



