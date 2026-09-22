"""Read models and audited corrections used by the Phase 4 admin interface."""

from calendar import monthrange
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text

from apps.api.admin import Page, paged
from apps.api.auth import require_admin
from apps.api.db import get_engine
from apps.api.jobs import JobConflict, RecordNotRetryable, enqueue_job

router = APIRouter(dependencies=[Depends(require_admin)], tags=["Operations"])


class DateCorrection(BaseModel):
    order_date: date
    reason: str = Field(min_length=5, max_length=500)


FollowUpStatus = Literal[
    "CONTACTED",
    "NO_ANSWER",
    "CALLBACK",
    "INTERESTED",
    "NOT_INTERESTED",
    "DO_NOT_CONTACT",
]
FollowUpChannel = Literal["CALL", "WHATSAPP", "EMAIL", "OTHER"]
FollowUpSentiment = Literal["NOT_RECORDED", "POSITIVE", "NEUTRAL", "MIXED", "NEGATIVE"]
PurchaseIntent = Literal["UNKNOWN", "HIGH", "MEDIUM", "LOW", "NONE"]
FeedbackTag = Literal[
    "POSITIVE_FEEDBACK",
    "PRODUCT_LIKED",
    "PRODUCT_DISLIKED",
    "HAS_CONCERNS",
    "PRICE_TOO_HIGH",
    "QUALITY_CONCERN",
    "PACKAGING_CONCERN",
    "DELIVERY_CONCERN",
    "RESULTS_NOT_SEEN",
    "WANTS_OFFER",
    "READY_TO_REORDER",
]
CustomerSegment = Literal[
    "CHAMPIONS",
    "LOYAL_REPEAT",
    "NEW_CUSTOMER",
    "HIGH_VALUE_ONE_TIME",
    "ACTIVE_ONE_TIME",
    "AT_RISK_REPEAT",
    "AT_RISK_HIGH_VALUE",
    "DORMANT_ONE_TIME",
]
CustomerTag = Literal[
    "RECENT_30D",
    "FIRST_TIME_BUYER",
    "REPEAT_BUYER",
    "HIGH_VALUE",
    "VIP_VALUE",
    "HAIR_COLOR",
    "HAIR_CARE",
    "SKIN_CARE",
    "HYDROSOL",
    "COMBO_BUYER",
]


class FollowUpInput(BaseModel):
    status: FollowUpStatus
    channel: FollowUpChannel = "CALL"
    contacted_by: str = Field(min_length=2, max_length=100)
    sentiment: FollowUpSentiment = "NOT_RECORDED"
    feedback_tags: list[FeedbackTag] = Field(default_factory=list)
    purchase_intent: PurchaseIntent = "UNKNOWN"
    offer_interest: bool = False
    expected_order_date: date | None = None
    notes: str | None = Field(default=None, max_length=1000)
    next_follow_up_at: datetime | None = None


class SegmentSettingsInput(BaseModel):
    new_customer_days: int = Field(ge=1, le=89)
    active_customer_days: int = Field(ge=30, le=365)
    champion_recency_days: int = Field(ge=1, le=365)
    champion_min_orders: int = Field(ge=3, le=20)
    high_value_percentile: float = Field(ge=0.5, le=0.95)
    vip_value_percentile: float = Field(ge=0.6, le=0.99)

    @model_validator(mode="after")
    def validate_boundaries(self) -> "SegmentSettingsInput":
        if self.new_customer_days >= self.active_customer_days:
            raise ValueError("New-customer days must be lower than active-customer days")
        if self.high_value_percentile >= self.vip_value_percentile:
            raise ValueError("High-value percentile must be lower than VIP percentile")
        return self


@router.get("/admin/dashboard")
def dashboard() -> dict:
    with get_engine().connect() as connection:
        return dict(
            connection.execute(
                text("""
            SELECT
                (SELECT count(*) FROM raw_order_ingestion WHERE status = 'NEW') AS pending,
                (SELECT count(*) FROM raw_order_ingestion WHERE status = 'PROCESSING')
                    AS processing,
                (SELECT count(*) FROM raw_order_ingestion WHERE status = 'PROCESSED') AS processed,
                (SELECT count(*) FROM raw_order_ingestion WHERE status = 'ERROR') AS errors,
                (SELECT count(*) FROM order_items WHERE mapping_status = 'PENDING')
                    AS pending_mappings,
                (SELECT count(*) FROM orders) AS order_count,
                (SELECT COALESCE(sum(order_value), 0) FROM orders) AS revenue,
                (SELECT COALESCE(avg(order_value), 0) FROM orders) AS average_order_value,
                (SELECT count(*) FROM customers) AS customer_count,
                (SELECT count(*) FROM (
                    SELECT customer_id FROM orders WHERE customer_id IS NOT NULL
                    GROUP BY customer_id HAVING count(*) > 1
                ) repeaters) AS repeat_customer_count
        """)
            )
            .mappings()
            .one()
        )


@router.get("/admin/analytics")
def analytics(
    year: int | None = Query(None, ge=2000, le=2099),
    month: int | None = Query(None, ge=1, le=12),
    window: Literal["year", "quarter"] = "year",
) -> dict:
    """Return revenue, product, and customer series at monthly or daily grain."""
    with get_engine().connect() as connection:
        available_years = [
            row[0]
            for row in connection.execute(
                text(
                    "SELECT DISTINCT EXTRACT(YEAR FROM order_date)::int "
                    "FROM orders ORDER BY 1 DESC"
                )
            ).all()
        ]
        selected_year = year or (available_years[0] if available_years else date.today().year)
        def move_month(value: date, offset: int) -> date:
            absolute = value.year * 12 + value.month - 1 + offset
            return date(absolute // 12, absolute % 12 + 1, 1)

        if month:
            start = date(selected_year, month, 1)
            end = move_month(start, 1)
            previous_end = start
            previous_start = move_month(start, -1)
            grain = "day"
            period_dates = [
                date(selected_year, month, day)
                for day in range(1, monthrange(selected_year, month)[1] + 1)
            ]
        elif window == "quarter":
            latest_order_date = connection.execute(
                text("""
                    SELECT max(order_date) FROM orders
                    WHERE EXTRACT(YEAR FROM order_date)::int = :year
                """),
                {"year": selected_year},
            ).scalar_one_or_none()
            anchor = date(
                selected_year,
                latest_order_date.month if latest_order_date else 12,
                1,
            )
            period_dates = [move_month(anchor, offset) for offset in (-2, -1, 0)]
            start = period_dates[0]
            end = move_month(anchor, 1)
            previous_end = start
            previous_start = move_month(start, -3)
            grain = "month"
        else:
            start = date(selected_year, 1, 1)
            end = date(selected_year + 1, 1, 1)
            previous_start = date(selected_year - 1, 1, 1)
            previous_end = start
            grain = "month"
            period_dates = [date(selected_year, value, 1) for value in range(1, 13)]

        def summary(period_start: date, period_end: date) -> dict:
            row = connection.execute(
                text("""
                    WITH scoped AS (
                        SELECT customer_id, order_value
                        FROM orders
                        WHERE order_date >= :start AND order_date < :end
                    )
                    SELECT count(*) AS order_count,
                        COALESCE(sum(order_value), 0) AS revenue,
                        COALESCE(avg(order_value), 0) AS average_order_value,
                        count(DISTINCT customer_id) AS active_customers,
                        (SELECT count(*) FROM (
                            SELECT customer_id FROM scoped WHERE customer_id IS NOT NULL
                            GROUP BY customer_id HAVING count(*) > 1
                        ) repeated) AS repeat_customers
                    FROM scoped
                """),
                {"start": period_start, "end": period_end},
            ).mappings().one()
            result = dict(row)
            result["new_customers"] = connection.execute(
                text("""
                    SELECT count(*) FROM customers
                    WHERE first_order_date >= :start AND first_order_date < :end
                """),
                {"start": period_start, "end": period_end},
            ).scalar_one()
            return result

        current = summary(start, end)
        previous = summary(previous_start, previous_end)

        order_rows = connection.execute(
            text(f"""
                SELECT date_trunc('{grain}', order_date)::date AS period,
                    COALESCE(sum(order_value), 0) AS revenue, count(*) AS orders
                FROM orders
                WHERE order_date >= :start AND order_date < :end
                GROUP BY period ORDER BY period
            """),
            {"start": start, "end": end},
        ).mappings().all()
        customer_rows = connection.execute(
            text(f"""
                SELECT date_trunc('{grain}', first_order_date)::date AS period,
                    count(*) AS new_customers
                FROM customers
                WHERE first_order_date >= :start AND first_order_date < :end
                GROUP BY period ORDER BY period
            """),
            {"start": start, "end": end},
        ).mappings().all()
        order_by_period = {row["period"]: row for row in order_rows}
        customers_by_period = {row["period"]: row["new_customers"] for row in customer_rows}
        periods = [
            {
                "period": value,
                "label": value.strftime("%b") if grain == "month" else str(value.day),
                "revenue": order_by_period.get(value, {}).get("revenue", 0),
                "orders": order_by_period.get(value, {}).get("orders", 0),
                "new_customers": customers_by_period.get(value, 0),
            }
            for value in period_dates
        ]

        product_rows = connection.execute(
            text(f"""
                SELECT date_trunc('{grain}', o.order_date)::date AS period,
                    COALESCE(p.canonical_name, NULLIF(trim(i.raw_product_name), ''),
                        'Unknown product') AS product_name,
                    COALESCE(sum(i.line_total), 0) AS revenue,
                    COALESCE(sum(i.quantity), 0) AS quantity
                FROM order_items i
                JOIN orders o ON o.id = i.order_id
                LEFT JOIN products p ON p.id = i.product_id
                WHERE o.order_date >= :start AND o.order_date < :end
                GROUP BY period, product_name
                ORDER BY period, product_name
            """),
            {"start": start, "end": end},
        ).mappings().all()
        product_totals: dict[str, dict] = {}
        for row in product_rows:
            item = product_totals.setdefault(
                row["product_name"], {"revenue": 0, "quantity": 0, "periods": {}}
            )
            item["revenue"] += row["revenue"]
            item["quantity"] += row["quantity"]
            item["periods"][row["period"]] = row["revenue"]
        top_names = sorted(
            product_totals,
            key=lambda name: product_totals[name]["revenue"],
            reverse=True,
        )[:5]
        products = [
            {
                "product_name": name,
                "revenue": product_totals[name]["revenue"],
                "quantity": product_totals[name]["quantity"],
                "values": [
                    product_totals[name]["periods"].get(value, 0) for value in period_dates
                ],
            }
            for name in top_names
        ]

        def change(current_value: object, previous_value: object) -> float | None:
            old = float(previous_value or 0)
            if old == 0:
                return None
            return round((float(current_value or 0) - old) * 100 / old, 1)

        return {
            "available_years": available_years or [selected_year],
            "selected_year": selected_year,
            "selected_month": month,
            "window": window,
            "grain": grain,
            "period_start": start,
            "period_end": end,
            "summary": {
                **current,
                "revenue_change": change(current["revenue"], previous["revenue"]),
                "order_change": change(current["order_count"], previous["order_count"]),
                "new_customer_change": change(
                    current["new_customers"], previous["new_customers"]
                ),
            },
            "periods": periods,
            "products": products,
        }


@router.get("/orders", response_model=Page)
def orders(
    search: str | None = Query(None, max_length=150),
    sort: Literal["order_date", "order_value", "item_count", "customer_name"] = "order_date",
    direction: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Page:
    order_by = {
        "order_date": "o.order_date",
        "order_value": "o.order_value",
        "item_count": "count(i.id)",
        "customer_name": "COALESCE(c.customer_name, '')",
    }[sort]
    sql = f"""
        SELECT o.id, o.source_record_id, o.source_system, o.order_date, o.order_value,
            o.payment_method, o.delivery_city, o.delivery_state, o.delivery_pincode,
            c.id AS customer_id, c.customer_name, c.normalized_phone,
            count(i.id) AS item_count,
            count(i.id) FILTER (WHERE i.mapping_status = 'PENDING') AS pending_items
        FROM orders o LEFT JOIN customers c ON c.id = o.customer_id
        LEFT JOIN order_items i ON i.order_id = o.id
        WHERE CAST(:search AS TEXT) IS NULL
           OR o.source_record_id ILIKE '%' || :search || '%'
           OR COALESCE(c.customer_name, '') ILIKE '%' || :search || '%'
           OR COALESCE(c.normalized_phone, '') ILIKE '%' || :search || '%'
           OR EXISTS (
               SELECT 1 FROM order_items searched
               LEFT JOIN products sp ON sp.id = searched.product_id
               LEFT JOIN product_variants sv ON sv.id = searched.variant_id
               WHERE searched.order_id = o.id AND (
                   searched.raw_product_name ILIKE '%' || :search || '%'
                   OR COALESCE(searched.raw_variant_name, '') ILIKE '%' || :search || '%'
                   OR COALESCE(sp.canonical_name, '') ILIKE '%' || :search || '%'
                   OR COALESCE(sv.variant_name, '') ILIKE '%' || :search || '%'
               )
           )
        GROUP BY o.id, c.id
        ORDER BY {order_by} {direction.upper()}, o.id
    """
    return paged(sql, {"search": search}, limit, offset)


@router.get("/orders/{order_id}")
def order_detail(order_id: UUID) -> dict:
    with get_engine().connect() as connection:
        order = (
            connection.execute(
                text("""
            SELECT o.*, c.customer_name, c.normalized_phone, c.email
            FROM orders o LEFT JOIN customers c ON c.id = o.customer_id WHERE o.id = :id
        """),
                {"id": order_id},
            )
            .mappings()
            .one_or_none()
        )
        if order is None:
            raise HTTPException(404, "Order not found")
        items = (
            connection.execute(
                text("""
            SELECT i.*, p.canonical_name, v.variant_name FROM order_items i
            LEFT JOIN products p ON p.id = i.product_id
            LEFT JOIN product_variants v ON v.id = i.variant_id
            WHERE i.order_id = :id ORDER BY i.created_at, i.id
        """),
                {"id": order_id},
            )
            .mappings()
            .all()
        )
        return {"order": dict(order), "items": [dict(item) for item in items]}


@router.get("/admin/customer-segment-settings")
def customer_segment_settings() -> dict:
    with get_engine().connect() as connection:
        return dict(
            connection.execute(
                text("""
                SELECT new_customer_days, active_customer_days, champion_recency_days,
                    champion_min_orders, high_value_percentile, vip_value_percentile,
                    updated_at
                FROM customer_segment_settings WHERE singleton
            """)
            ).mappings().one()
        )


@router.put("/admin/customer-segment-settings")
def update_customer_segment_settings(data: SegmentSettingsInput) -> dict:
    with get_engine().begin() as connection:
        return dict(
            connection.execute(
                text("""
                UPDATE customer_segment_settings SET
                    new_customer_days = :new_days,
                    active_customer_days = :active_days,
                    champion_recency_days = :champion_days,
                    champion_min_orders = :champion_orders,
                    high_value_percentile = :high_percentile,
                    vip_value_percentile = :vip_percentile,
                    updated_at = NOW()
                WHERE singleton
                RETURNING new_customer_days, active_customer_days,
                    champion_recency_days, champion_min_orders,
                    high_value_percentile, vip_value_percentile, updated_at
            """),
                {
                    "new_days": data.new_customer_days,
                    "active_days": data.active_customer_days,
                    "champion_days": data.champion_recency_days,
                    "champion_orders": data.champion_min_orders,
                    "high_percentile": data.high_value_percentile,
                    "vip_percentile": data.vip_value_percentile,
                },
            ).mappings().one()
        )


@router.get("/admin/customer-segments")
def customer_segments() -> dict:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text("""
            SELECT segment, count(*) AS customer_count,
                COALESCE(sum(lifetime_value), 0) AS lifetime_value,
                COALESCE(avg(lifetime_value), 0) AS average_lifetime_value,
                COALESCE(sum(order_count), 0) AS order_count
            FROM customer_analysis
            GROUP BY segment
            ORDER BY CASE segment
                WHEN 'CHAMPIONS' THEN 1 WHEN 'LOYAL_REPEAT' THEN 2
                WHEN 'NEW_CUSTOMER' THEN 3 WHEN 'HIGH_VALUE_ONE_TIME' THEN 4
                WHEN 'AT_RISK_REPEAT' THEN 5 WHEN 'AT_RISK_HIGH_VALUE' THEN 6
                WHEN 'ACTIVE_ONE_TIME' THEN 7 ELSE 8 END
        """)
        ).mappings().all()
        tags = connection.execute(
            text("""
            SELECT tag, count(*) AS customer_count
            FROM customer_analysis CROSS JOIN LATERAL unnest(tags) AS tag
            GROUP BY tag ORDER BY customer_count DESC, tag
        """)
        ).mappings().all()
        thresholds = connection.execute(
            text("""
            SELECT max(high_value_threshold) AS high_value,
                max(vip_value_threshold) AS vip_value,
                max(last_order_date) AS latest_order_date
            FROM customer_analysis
        """)
        ).mappings().one()
        settings = connection.execute(
            text("""
            SELECT new_customer_days, active_customer_days, champion_recency_days,
                champion_min_orders, high_value_percentile, vip_value_percentile,
                updated_at
            FROM customer_segment_settings WHERE singleton
        """)
        ).mappings().one()
        return {
            "segments": [dict(row) for row in rows],
            "tags": [dict(row) for row in tags],
            "thresholds": dict(thresholds),
            "settings": dict(settings),
        }


@router.get("/customers", response_model=Page)
def customers(
    search: str | None = Query(None, max_length=150),
    segment: CustomerSegment | None = None,
    tag: CustomerTag | None = None,
    sales_signal: Literal["HIGH_INTENT", "OFFER_INTEREST", "CONCERNS", "PRICE_HIGH"]
    | None = None,
    follow_up_status: Literal[
        "NOT_CONTACTED",
        "CONTACTED",
        "NO_ANSWER",
        "CALLBACK",
        "INTERESTED",
        "NOT_INTERESTED",
        "DO_NOT_CONTACT",
    ]
    | None = None,
    sort: Literal[
        "last_order_date",
        "first_order_date",
        "lifetime_value",
        "order_count",
        "customer_name",
        "recency_days",
        "segment",
        "last_follow_up_at",
        "next_follow_up_at",
    ] = "last_order_date",
    direction: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Page:
    order_by = {
        "last_order_date": "ca.last_order_date",
        "first_order_date": "ca.first_order_date",
        "lifetime_value": "ca.lifetime_value",
        "order_count": "ca.order_count",
        "customer_name": "COALESCE(c.customer_name, '')",
        "recency_days": "ca.recency_days",
        "segment": "ca.segment",
        "last_follow_up_at": "lf.contacted_at",
        "next_follow_up_at": "lf.next_follow_up_at",
    }[sort]
    sql = f"""
        SELECT c.id, c.customer_name, c.normalized_phone, c.email,
            ca.first_order_date, ca.last_order_date, ca.order_count,
            ca.lifetime_value, ca.average_order_value, ca.recency_days,
            ca.segment, ca.tags,
            COALESCE(lf.status, 'NOT_CONTACTED') AS follow_up_status,
            lf.channel AS follow_up_channel, lf.contacted_by AS last_follow_up_by,
            lf.contacted_at AS last_follow_up_at, lf.next_follow_up_at,
            lf.sentiment AS latest_sentiment, lf.feedback_tags AS latest_feedback_tags,
            lf.purchase_intent AS latest_purchase_intent,
            lf.offer_interest AS latest_offer_interest,
            lf.expected_order_date AS latest_expected_order_date
        FROM customers c
        JOIN customer_analysis ca ON ca.customer_id = c.id
        LEFT JOIN LATERAL (
            SELECT id, status, channel, contacted_by, contacted_at, next_follow_up_at,
                sentiment, feedback_tags, purchase_intent, offer_interest,
                expected_order_date
            FROM customer_follow_ups
            WHERE customer_id = c.id
            ORDER BY contacted_at DESC, id DESC LIMIT 1
        ) lf ON TRUE
        WHERE (
           CAST(:search AS TEXT) IS NULL
           OR COALESCE(c.customer_name, '') ILIKE '%' || :search || '%'
           OR COALESCE(c.normalized_phone, '') ILIKE '%' || :search || '%'
           OR COALESCE(c.email, '') ILIKE '%' || :search || '%'
           OR EXISTS (
               SELECT 1 FROM orders searched_order
               JOIN order_items searched_item ON searched_item.order_id = searched_order.id
               LEFT JOIN products sp ON sp.id = searched_item.product_id
               LEFT JOIN product_variants sv ON sv.id = searched_item.variant_id
               WHERE searched_order.customer_id = c.id AND (
                   searched_item.raw_product_name ILIKE '%' || :search || '%'
                   OR COALESCE(searched_item.raw_variant_name, '') ILIKE '%' || :search || '%'
                   OR COALESCE(sp.canonical_name, '') ILIKE '%' || :search || '%'
                   OR COALESCE(sv.variant_name, '') ILIKE '%' || :search || '%'
               )
           )
        ) AND (
            CAST(:follow_up_status AS TEXT) IS NULL
            OR (:follow_up_status = 'NOT_CONTACTED' AND lf.id IS NULL)
            OR lf.status = :follow_up_status
        ) AND (CAST(:segment AS TEXT) IS NULL OR ca.segment = :segment)
          AND (CAST(:tag AS TEXT) IS NULL OR CAST(:tag AS TEXT) = ANY(ca.tags))
          AND (
            CAST(:sales_signal AS TEXT) IS NULL
            OR (:sales_signal = 'HIGH_INTENT' AND lf.purchase_intent = 'HIGH')
            OR (:sales_signal = 'OFFER_INTEREST' AND lf.offer_interest)
            OR (:sales_signal = 'CONCERNS' AND 'HAS_CONCERNS' = ANY(lf.feedback_tags))
            OR (:sales_signal = 'PRICE_HIGH' AND 'PRICE_TOO_HIGH' = ANY(lf.feedback_tags))
          )
        ORDER BY {order_by} {direction.upper()} NULLS LAST, c.id
    """
    return paged(
        sql,
        {
            "search": search,
            "follow_up_status": follow_up_status,
            "segment": segment,
            "tag": tag,
            "sales_signal": sales_signal,
        },
        limit,
        offset,
    )


@router.get("/customers/{customer_id}")
def customer_detail(customer_id: UUID) -> dict:
    with get_engine().connect() as connection:
        customer = (
            connection.execute(text("SELECT * FROM customers WHERE id = :id"), {"id": customer_id})
            .mappings()
            .one_or_none()
        )
        if customer is None:
            raise HTTPException(404, "Customer not found")
        orders = (
            connection.execute(
                text("""
            SELECT id, source_record_id, order_date, order_value, payment_method,
                delivery_city, delivery_state, delivery_pincode
            FROM orders WHERE customer_id = :id ORDER BY order_date DESC, id
        """),
                {"id": customer_id},
            )
            .mappings()
            .all()
        )
        follow_ups = (
            connection.execute(
                text("""
            SELECT id, status, channel, contacted_by, sentiment, feedback_tags,
                purchase_intent, offer_interest, expected_order_date,
                notes, contacted_at, next_follow_up_at
            FROM customer_follow_ups
            WHERE customer_id = :id ORDER BY contacted_at DESC, id DESC
        """),
                {"id": customer_id},
            )
            .mappings()
            .all()
        )
        return {
            "customer": dict(customer),
            "orders": [dict(order) for order in orders],
            "follow_ups": [dict(item) for item in follow_ups],
        }


@router.post("/admin/customers/{customer_id}/follow-ups", status_code=201)
def create_customer_follow_up(customer_id: UUID, data: FollowUpInput) -> dict:
    contacted_by = data.contacted_by.strip()
    notes = data.notes.strip() if data.notes and data.notes.strip() else None
    with get_engine().begin() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM customers WHERE id = :id FOR UPDATE"),
            {"id": customer_id},
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(404, "Customer not found")
        return dict(
            connection.execute(
                text("""
                INSERT INTO customer_follow_ups (
                    customer_id, status, channel, contacted_by, sentiment,
                    feedback_tags, purchase_intent, offer_interest,
                    expected_order_date, notes, next_follow_up_at
                ) VALUES (
                    :customer_id, :status, :channel, :contacted_by, :sentiment,
                    :feedback_tags, :purchase_intent, :offer_interest,
                    :expected_order_date, :notes, :next_at
                )
                RETURNING id, customer_id, status, channel, contacted_by,
                    sentiment, feedback_tags, purchase_intent, offer_interest,
                    expected_order_date, notes, contacted_at, next_follow_up_at
            """),
                {
                    "customer_id": customer_id,
                    "status": data.status,
                    "channel": data.channel,
                    "contacted_by": contacted_by,
                    "sentiment": data.sentiment,
                    "feedback_tags": list(dict.fromkeys(data.feedback_tags)),
                    "purchase_intent": data.purchase_intent,
                    "offer_interest": data.offer_interest
                    or "WANTS_OFFER" in data.feedback_tags,
                    "expected_order_date": data.expected_order_date,
                    "notes": notes,
                    "next_at": data.next_follow_up_at,
                },
            )
            .mappings()
            .one()
        )


@router.put("/admin/ingestion/{ingestion_id}/order-date", status_code=202)
def correct_order_date(ingestion_id: UUID, data: DateCorrection) -> dict:
    with get_engine().begin() as connection:
        record = (
            connection.execute(
                text("SELECT status FROM raw_order_ingestion WHERE id = :id FOR UPDATE"),
                {"id": ingestion_id},
            )
            .mappings()
            .one_or_none()
        )
        if record is None:
            raise HTTPException(404, "Ingestion record not found")
        if record["status"] != "ERROR":
            raise HTTPException(409, "Only ERROR records can be corrected")
        connection.execute(
            text("""
            INSERT INTO order_corrections (ingestion_id, order_date, reason)
            VALUES (:id, :day, :reason)
            ON CONFLICT (ingestion_id) DO UPDATE SET order_date = EXCLUDED.order_date,
                reason = EXCLUDED.reason, updated_at = NOW()
        """),
            {"id": ingestion_id, "day": data.order_date, "reason": data.reason.strip()},
        )
    try:
        return enqueue_job(get_engine(), "RETRY_ONE", ingestion_id)
    except (JobConflict, RecordNotRetryable) as exc:
        raise HTTPException(409, str(exc)) from None


