"""Durable PostgreSQL jobs. No HTTP request executes order processing."""

import json
import logging
from uuid import UUID

from sqlalchemy import Engine, text

from apps.api.order_processing import process_single_order

logger = logging.getLogger("thaazhai.jobs")
WORKER_LOCK = 748192040
QUEUE_LOCK = 748192041
KINDS = {"PROCESS_PENDING", "RETRY_ERRORS", "RETRY_ONE", "RESOLVE_MAPPINGS"}


class JobConflict(ValueError):
    pass


class RecordNotRetryable(ValueError):
    pass


def enqueue_job(engine: Engine, kind: str, ingestion_id: UUID | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError("Unsupported job type")
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": QUEUE_LOCK})
        active = connection.execute(
            text("SELECT id FROM processing_jobs WHERE status IN ('QUEUED','RUNNING')")
        ).scalar_one_or_none()
        if active:
            raise JobConflict(f"Job {active} is already active")
        if kind == "RETRY_ONE":
            state = connection.execute(
                text("SELECT status FROM raw_order_ingestion WHERE id = :id"), {"id": ingestion_id}
            ).scalar_one_or_none()
            if state != "ERROR":
                raise RecordNotRetryable("The selected record must exist and have ERROR status")
        job_id = connection.execute(
            text("INSERT INTO processing_jobs (job_type) VALUES (:kind) RETURNING id"),
            {"kind": kind},
        ).scalar_one()
        predicates = {
            "PROCESS_PENDING": "r.status = 'NEW'",
            "RETRY_ERRORS": "r.status = 'ERROR'",
            "RETRY_ONE": "r.status = 'ERROR' AND r.id = :id",
            "RESOLVE_MAPPINGS": """EXISTS (
                SELECT 1 FROM orders o JOIN order_items i ON i.order_id = o.id
                WHERE o.ingestion_id = r.id AND i.mapping_status = 'PENDING'
            )""",
        }
        connection.execute(
            text(f"""
            INSERT INTO processing_job_items (job_id, ingestion_id)
            SELECT :job_id, r.id FROM raw_order_ingestion r WHERE {predicates[kind]}
        """),
            {"job_id": job_id, "id": ingestion_id},
        )
        return dict(
            connection.execute(
                text("""
            UPDATE processing_jobs SET total_records = (
                SELECT count(*) FROM processing_job_items WHERE job_id = :id
            ) WHERE id = :id RETURNING *
        """),
                {"id": job_id},
            )
            .mappings()
            .one()
        )


def run_next_job(engine: Engine, batch_size: int = 50) -> bool:
    """One worker holds the session lock; another worker exits without claiming work."""
    with engine.connect() as lock:
        acquired = lock.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": WORKER_LOCK}
        ).scalar_one()
        lock.commit()
        if not acquired:
            return False
        job_id = None
        try:
            with engine.begin() as connection:
                job = (
                    connection.execute(
                        text("""
                    SELECT * FROM processing_jobs WHERE status IN ('RUNNING','QUEUED')
                    ORDER BY CASE WHEN status = 'RUNNING' THEN 0 ELSE 1 END, created_at
                    LIMIT 1 FOR UPDATE SKIP LOCKED
                """)
                    )
                    .mappings()
                    .one_or_none()
                )
                if job is None:
                    return False
                job_id = job["id"]
                connection.execute(
                    text("""
                    UPDATE processing_jobs SET status = 'RUNNING',
                        started_at = COALESCE(started_at, NOW()) WHERE id = :id
                """),
                    {"id": job_id},
                )
            while True:
                # Verify the lock-owning session still exists before processing more work.
                lock.execute(text("SELECT 1"))
                lock.commit()
                with engine.connect() as connection:
                    ids = (
                        connection.execute(
                            text("""
                        SELECT ingestion_id FROM processing_job_items
                        WHERE job_id = :id AND status = 'PENDING'
                        ORDER BY ingestion_id LIMIT :batch
                    """),
                            {"id": job_id, "batch": batch_size},
                        )
                        .scalars()
                        .all()
                    )
                if not ids:
                    break
                for ingestion_id in ids:
                    with engine.begin() as connection:
                        item = connection.execute(
                            text("""
                            SELECT status FROM processing_job_items
                            WHERE job_id = :job AND ingestion_id = :raw
                            FOR UPDATE
                        """),
                            {"job": job_id, "raw": ingestion_id},
                        ).scalar_one()
                        if item != "PENDING":
                            continue
                        result = process_single_order(
                            connection,
                            ingestion_id,
                            retry_error=job["job_type"] in ("RETRY_ERRORS", "RETRY_ONE"),
                        )
                        if result.status == "UNAVAILABLE":
                            # A manual operation holds this record; retry in the next worker tick.
                            return True
                        succeeded = result.status == "PROCESSED"
                        if job["job_type"] == "RESOLVE_MAPPINGS" and result.pending_items:
                            succeeded = False
                        error = (
                            None
                            if succeeded
                            else (
                                result.error
                                or "Order remains unmapped or is not eligible for processing"
                            )
                        )
                        connection.execute(
                            text("""
                            UPDATE processing_job_items SET status = :status,
                                error_message = :error, completed_at = NOW()
                            WHERE job_id = :job AND ingestion_id = :raw
                        """),
                            {
                                "status": "SUCCESS" if succeeded else "FAILED",
                                "error": error,
                                "job": job_id,
                                "raw": ingestion_id,
                            },
                        )
                        connection.execute(
                            text("""
                            UPDATE processing_jobs SET processed_count = processed_count + 1,
                                success_count = success_count + :success,
                                failed_count = failed_count + :failed WHERE id = :id
                        """),
                            {"success": int(succeeded), "failed": int(not succeeded), "id": job_id},
                        )
            with engine.begin() as connection:
                connection.execute(
                    text("""
                    UPDATE processing_jobs SET status = 'COMPLETED', completed_at = NOW()
                    WHERE id = :id
                """),
                    {"id": job_id},
                )
            return True
        except Exception as exc:
            logger.error(
                json.dumps({"event": "worker_job_failed", "error_type": type(exc).__name__})
            )
            # Infrastructure failures leave RUNNING/PENDING work recoverable on the next tick.
            raise
        finally:
            try:
                lock.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": WORKER_LOCK})
                lock.commit()
            except Exception:
                lock.invalidate()
