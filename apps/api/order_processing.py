"""One raw order per transaction. HTTP/job orchestration arrives in Phase 3."""

import json
import logging
from contextlib import nullcontext
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from apps.api.location import normalize_delivery_location
from apps.api.normalization import (
    OrderValidationError,
    money,
    normalize_phone,
    optional_text,
    parse_order_date,
    required_text,
)
from apps.api.product_resolver import MappingPending, resolve_product

logger = logging.getLogger("thaazhai.processing")


@dataclass(frozen=True)
class ProcessResult:
    ingestion_id: UUID
    status: str
    order_id: UUID | None = None
    error: str | None = None
    pending_items: int = 0


def create_normalized_order(connection: Connection, raw: dict) -> UUID:
    if raw["source_system"] != "HOSTINGER":
        raise OrderValidationError("Unsupported source_system; only HOSTINGER is implemented")
    source_id = required_text(raw["source_record_id"], "source_record_id", 150)
    payload = raw["raw_payload"]
    if not isinstance(payload, dict):
        raise OrderValidationError("raw_payload must be an object")
    payload_id = payload.get("order_id")
    if isinstance(payload_id, bool) or not isinstance(payload_id, (str, int)):
        raise OrderValidationError("payload order_id is required")
    if str(payload_id) != source_id:
        raise OrderValidationError("payload order_id does not match source_record_id")
    correction = (
        connection.execute(
            text("SELECT order_date FROM order_corrections WHERE ingestion_id = :id"),
            {"id": raw["id"]},
        )
        .mappings()
        .one_or_none()
    )
    order_date = (
        correction["order_date"]
        if correction and correction["order_date"]
        else parse_order_date(payload.get("order_date"))
    )
    phone = normalize_phone(payload.get("phone"))
    total = money(payload.get("total"), "total")
    name = optional_text(payload.get("customer_name"), "customer_name", 255)
    email = optional_text(payload.get("email"), "email", 255)
    payment = optional_text(payload.get("payment_method"), "payment_method", 100)
    address = payload.get("address")
    if address is not None and not isinstance(address, dict):
        raise OrderValidationError("address must be an object")
    location = normalize_delivery_location(address)
    products = payload.get("products")
    if not isinstance(products, list) or not products:
        raise OrderValidationError("products must contain at least one item")

    resolved = []
    for item in products:
        if not isinstance(item, dict):
            raise OrderValidationError("Each product must be an object")
        raw_name = required_text(item.get("product"), "product", 255)
        raw_variant = optional_text(item.get("variant"), "variant", 150)
        quantity = item.get("quantity")
        if type(quantity) is not int or not 1 <= quantity <= 2147483647:
            raise OrderValidationError("quantity must be a positive integer")
        unit_price = money(item.get("unit_price"), "unit_price")
        line_total = money(unit_price * quantity, "line_total")
        mapping_status, mapping_error = "RESOLVED", None
        try:
            product_id, variant_id = resolve_product(
                connection, raw["source_system"], raw_name, raw_variant
            )
        except MappingPending as exc:
            product_id, variant_id = None, None
            mapping_status, mapping_error = "PENDING", str(exc)
        resolved.append(
            {
                "mapping_status": mapping_status,
                "mapping_error": mapping_error,
                "product_id": product_id,
                "variant_id": variant_id,
                "raw_product_name": raw_name,
                "raw_variant_name": raw_variant,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": line_total,
            }
        )

    # All items validate before writes; pending catalogue matches retain the sale.
    customer_id = connection.execute(
        text("""
        INSERT INTO customers
            (customer_name, normalized_phone, email, first_order_date, last_order_date)
        VALUES (:name, :phone, :email, :day, :day)
        ON CONFLICT (normalized_phone) WHERE normalized_phone IS NOT NULL
        DO UPDATE SET
            first_order_date = LEAST(customers.first_order_date, EXCLUDED.first_order_date),
            last_order_date = GREATEST(customers.last_order_date, EXCLUDED.last_order_date),
            updated_at = NOW()
        RETURNING id
    """),
        {"name": name, "phone": phone, "email": email, "day": order_date},
    ).scalar_one()
    order_id = connection.execute(
        text("""
        INSERT INTO orders
            (ingestion_id, customer_id, source_system, source_record_id,
             order_date, payment_method, order_value, address,
             delivery_city, delivery_state, delivery_country, delivery_pincode,
             delivery_location_sources)
        VALUES (:ingestion_id, :customer_id, :source, :source_id,
                :day, :payment, :total, CAST(:address AS JSONB),
                :delivery_city, :delivery_state, :delivery_country, :delivery_pincode,
                CAST(:delivery_location_sources AS JSONB))
        RETURNING id
    """),
        {
            "ingestion_id": raw["id"],
            "customer_id": customer_id,
            "source": raw["source_system"],
            "source_id": source_id,
            "day": order_date,
            "payment": payment,
            "total": total,
            "address": json.dumps(address) if address is not None else None,
            **location,
            "delivery_location_sources": json.dumps(location["delivery_location_sources"]),
        },
    ).scalar_one()
    for item in resolved:
        connection.execute(
            text("""
            INSERT INTO order_items
                (order_id, product_id, variant_id, raw_product_name,
                 raw_variant_name, quantity, unit_price, line_total, mapping_status, mapping_error)
            VALUES (:order_id, :product_id, :variant_id, :raw_product_name,
                    :raw_variant_name, :quantity, :unit_price, :line_total,
                    :mapping_status, :mapping_error)
        """),
            {"order_id": order_id, **item},
        )
    return order_id


def pending_count(connection: Connection, order_id: UUID) -> int:
    return connection.execute(
        text("""
        SELECT count(*) FROM order_items WHERE order_id = :id AND mapping_status = 'PENDING'
    """),
        {"id": order_id},
    ).scalar_one()


def refresh_pending_mappings(connection: Connection, order_id: UUID, source: str) -> int:
    items = (
        connection.execute(
            text("""
        SELECT id, raw_product_name, raw_variant_name FROM order_items
        WHERE order_id = :id AND mapping_status = 'PENDING' FOR UPDATE
    """),
            {"id": order_id},
        )
        .mappings()
        .all()
    )
    for item in items:
        try:
            product_id, variant_id = resolve_product(
                connection, source, item["raw_product_name"], item["raw_variant_name"]
            )
        except MappingPending as exc:
            connection.execute(
                text("""
                UPDATE order_items SET mapping_error = :error WHERE id = :id
            """),
                {"id": item["id"], "error": str(exc)},
            )
        else:
            connection.execute(
                text("""
                UPDATE order_items SET product_id = :product_id, variant_id = :variant_id,
                    mapping_status = 'RESOLVED', mapping_error = NULL WHERE id = :id
            """),
                {"id": item["id"], "product_id": product_id, "variant_id": variant_id},
            )
    return pending_count(connection, order_id)


def process_single_order(
    engine: Engine | Connection, ingestion_id: UUID, *, retry_error: bool = False
) -> ProcessResult:
    with nullcontext(engine) if isinstance(engine, Connection) else engine.begin() as connection:
        raw = (
            connection.execute(
                text("""
            SELECT * FROM raw_order_ingestion WHERE id = :id
            FOR UPDATE SKIP LOCKED
        """),
                {"id": ingestion_id},
            )
            .mappings()
            .one_or_none()
        )
        if raw is None:
            return ProcessResult(ingestion_id, "UNAVAILABLE")
        existing = (
            connection.execute(
                text("""
            SELECT id, ingestion_id FROM orders
            WHERE source_system = :source AND source_record_id = :source_id
        """),
                {
                    "source": raw["source_system"],
                    "source_id": raw["source_record_id"],
                },
            )
            .mappings()
            .one_or_none()
        )
        if existing and existing["ingestion_id"] == ingestion_id:
            # Existing sale: repair only pending mappings, never duplicate the order.
            pending = refresh_pending_mappings(connection, existing["id"], raw["source_system"])
            connection.execute(
                text("""
                UPDATE raw_order_ingestion SET status = 'PROCESSED', error_message = NULL,
                    processed_at = COALESCE(processed_at, NOW()), updated_at = NOW()
                WHERE id = :id
            """),
                {"id": ingestion_id},
            )
            return ProcessResult(ingestion_id, "PROCESSED", existing["id"], pending_items=pending)
        if raw["status"] != "NEW" and not (raw["status"] == "ERROR" and retry_error):
            return ProcessResult(ingestion_id, "SKIPPED")
        connection.execute(
            text("""
            UPDATE raw_order_ingestion SET status = 'PROCESSING',
                processing_started_at = NOW(), processed_at = NULL, error_message = NULL,
                retry_count = retry_count + :retry, updated_at = NOW() WHERE id = :id
        """),
            {"id": ingestion_id, "retry": int(raw["status"] == "ERROR")},
        )
        try:
            # Savepoint rolls back every normalized write while allowing ERROR
            # metadata to be committed in the surrounding transaction.
            with connection.begin_nested():
                if existing:
                    raise OrderValidationError("Source order already belongs to another ingestion")
                order_id = create_normalized_order(connection, dict(raw))
                pending = pending_count(connection, order_id)
        except Exception as exc:
            error = (
                str(exc)
                if isinstance(exc, OrderValidationError)
                else ("Internal processing error; see processing logs for error type")
            )
            connection.execute(
                text("""
                UPDATE raw_order_ingestion SET status = 'ERROR', error_message = :error,
                    updated_at = NOW() WHERE id = :id
            """),
                {"id": ingestion_id, "error": error},
            )
            logger.warning(
                json.dumps(
                    {
                        "event": "order_processing_failed",
                        "ingestion_id": str(ingestion_id),
                        "error_type": type(exc).__name__,
                    }
                )
            )
            return ProcessResult(ingestion_id, "ERROR", error=error)
        connection.execute(
            text("""
            UPDATE raw_order_ingestion SET status = 'PROCESSED', processed_at = NOW(),
                error_message = NULL, updated_at = NOW() WHERE id = :id
        """),
            {"id": ingestion_id},
        )
    logger.info(
        json.dumps(
            {
                "event": "order_processed",
                "ingestion_id": str(ingestion_id),
                "order_id": str(order_id),
            }
        )
    )
    return ProcessResult(ingestion_id, "PROCESSED", order_id, pending_items=pending)
