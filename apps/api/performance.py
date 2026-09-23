"""Business comparisons from stored orders and Meta facts; never triggers a sync."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import text

from apps.api.auth import require_admin
from apps.api.db import get_engine
from apps.api.marketing import overview, ratio

router = APIRouter(prefix="/admin/performance", dependencies=[Depends(require_admin)])
Period = Literal["today", "yesterday", "week", "month"]
ONE_DAY = timedelta(days=1)


def comparison_window(period: Period, today: date) -> dict:
    """Week/month use equal numbers of completed calendar days, excluding today."""
    note = ""
    if period == "today":
        start = end = today
        previous_start = previous_end = today - ONE_DAY
        note = "Today is partial; yesterday is a full day. Percentage verdicts are withheld."
    elif period == "yesterday":
        start = end = today - ONE_DAY
        previous_start = previous_end = today - 2 * ONE_DAY
    else:
        start = (
            today - timedelta(days=today.weekday()) if period == "week" else today.replace(day=1)
        )
        previous_start = (
            start - timedelta(days=7) if period == "week" else (start - ONE_DAY).replace(day=1)
        )
        elapsed = (today - start).days
        previous_length = (start - previous_start).days
        days = min(elapsed, previous_length)
        if not days:
            return {
                "current_start": start,
                "current_end": None,
                "previous_start": previous_start,
                "previous_end": None,
                "days": 0,
                "partial": False,
                "note": "No completed days in this period yet. Choose Yesterday or Today.",
            }
        end = start + (days - 1) * ONE_DAY
        previous_end = previous_start + (days - 1) * ONE_DAY
        note = "Equal completed days; today is excluded. Weeks start on Monday."
        if elapsed > previous_length:
            note = "Both months are limited to the first %s days to match the shorter month." % days
    return {
        "current_start": start,
        "current_end": end,
        "previous_start": previous_start,
        "previous_end": previous_end,
        "days": (end - start).days + 1,
        "partial": period == "today",
        "note": note,
    }


def delta(current, previous, comparable=True) -> dict:
    if not comparable or current is None or previous is None:
        return {"absolute": None, "percent": None, "state": "unavailable"}
    current, previous = Decimal(str(current)), Decimal(str(previous))
    if previous == 0:
        return {
            "absolute": current - previous,
            "percent": Decimal(0) if current == 0 else None,
            "state": "unchanged" if current == 0 else "no_baseline",
        }
    return {
        "absolute": current - previous,
        "percent": ratio((current - previous) * 100, abs(previous)),
        "state": "compared",
    }


def period_values(report: dict, repeat_revenue) -> dict:
    business, meta = report["business"], report["meta"]
    # Coverage, not the presence of fact rows, distinguishes unknown spend from zero.
    covered = report["coverage"]["unsynced_days"] == 0
    spend = meta["spend"] if covered else None
    currency = (report["context"].get("account") or {}).get("currency")
    aligned = covered and currency == "INR"
    revenue = business["revenue"]
    return {
        "revenue": revenue,
        "orders": business["orders"],
        "aov": ratio(revenue, business["orders"]),
        "new_customers": business["new_customers"],
        "repeat_revenue": repeat_revenue,
        "spend": spend,
        "mer": ratio(revenue, spend) if aligned else None,
        "spend_per_new_customer": ratio(spend, business["new_customers"]) if aligned else None,
        "meta_roas": meta["meta_roas"] if covered else None,
    }


def compare_values(
    current: dict, previous: dict, partial: bool, current_order_gap: bool, previous_order_gap: bool
) -> dict:
    current, previous = dict(current), dict(previous)
    for values, gap in [(current, current_order_gap), (previous, previous_order_gap)]:
        if gap:
            values["mer"] = values["spend_per_new_customer"] = None
    return {
        key: {
            "current": value,
            "previous": previous[key],
            "change": delta(
                value,
                previous[key],
                not partial
                and (
                    key in ("spend", "meta_roas") or not (current_order_gap or previous_order_gap)
                ),
            ),
        }
        for key, value in current.items()
    }


def insight_messages(metrics: dict, partial: bool) -> list[str]:
    if partial:
        return [
            "Today's figures are still accumulating. Use Yesterday for a completed-day comparison."
        ]
    messages = []
    revenue = metrics["revenue"]["change"]
    orders = metrics["orders"]["change"]
    if revenue["percent"] is not None and orders["percent"] is not None:
        messages.append(
            f"Recorded sales changed {revenue['percent']:+}% and orders "
            f"{orders['percent']:+}% across the matched dates."
        )
    elif revenue["state"] == "unavailable":
        messages.append(
            "Order history does not extend through the compared dates. Sales changes and "
            "blended efficiency are withheld until order coverage is checked."
        )
    elif revenue["state"] == "no_baseline":
        messages.append(
            "The previous period has zero recorded sales; a growth percentage is undefined."
        )
    spend = metrics["spend"]["change"]
    if spend["state"] == "unavailable":
        messages.append(
            "Meta coverage is incomplete. Spend and efficiency comparisons are withheld."
        )
    elif spend["percent"] is not None and revenue["percent"] is not None:
        if spend["percent"] > revenue["percent"]:
            messages.append(
                "Ad spend changed faster than recorded sales. "
                "Review campaign results and order-feed "
                "freshness before changing budgets; this does not establish an advertising effect."
            )
        else:
            messages.append(
                "Recorded sales held up relative to the change in Meta spend. "
                "This comparison measures revenue efficiency, not profit."
            )
    messages.append(
        "New customers means first purchase in the available order history. "
        "Meta spend per new customer is blended, not campaign-attributed acquisition cost."
    )
    return messages


@router.get("")
def performance(period: Period = "week") -> dict:
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    window = comparison_window(period, now.date())
    with get_engine().connect() as connection:
        latest = connection.execute(text("SELECT max(order_date) FROM orders")).scalar_one()
    result = {
        "period": period,
        "timezone": "Asia/Kolkata",
        "generated_at": now,
        "window": window,
        "latest_order_date": latest,
        "order_coverage": "unverified",
        "order_note": (
            "Sales reflect processed orders currently available. "
            "The latest order date is not proof "
            "of a complete feed; local orders may be an imported snapshot."
        ),
        "metrics": {},
        "daily": [],
        "insights": [],
        "meta": None,
    }
    if not window["days"]:
        return result
    current = overview(window["current_start"], window["current_end"])
    previous = overview(window["previous_start"], window["previous_end"])
    # Classify repeat revenue at the order date, not by the customer's present-day bucket.
    # A second order on the first purchase day is not counted as returning-day revenue.
    with get_engine().connect() as connection:
        repeats = []
        for start, end in [
            (window["current_start"], window["current_end"]),
            (window["previous_start"], window["previous_end"]),
        ]:
            repeats.append(
                connection.execute(
                    text("""
                SELECT COALESCE(sum(o.order_value), 0)
                FROM orders o JOIN customers c ON c.id = o.customer_id
                WHERE o.order_date BETWEEN :start AND :end
                  AND c.first_order_date < o.order_date
            """),
                    {"start": start, "end": end},
                ).scalar_one()
            )
    current_values = period_values(current, repeats[0])
    previous_values = period_values(previous, repeats[1])
    current_order_gap = latest is None or latest < window["current_end"]
    previous_order_gap = latest is None or latest < window["previous_end"]
    metrics = compare_values(
        current_values,
        previous_values,
        window["partial"],
        current_order_gap,
        previous_order_gap,
    )
    result["order_date_gap"] = current_order_gap or previous_order_gap
    if result["order_date_gap"]:
        result["order_note"] += (
            " No orders are recorded through the end of the comparison. "
            "Sales percentage changes and blended ratios are withheld; "
            "recorded totals remain visible. A quiet sales day and a missing feed "
            "cannot be distinguished automatically."
        )
    result.update(
        {
            "metrics": metrics,
            "insights": insight_messages(metrics, window["partial"]),
            "daily": [
                {"current": a, "previous": b}
                for a, b in zip(current["daily"], previous["daily"], strict=True)
            ],
            "meta": {
                "currency": (current["context"].get("account") or {}).get("currency"),
                "current_coverage": current["coverage"],
                "previous_coverage": previous["coverage"],
                "last_successful_sync": current["context"]["last_successful_sync"],
                "last_data_date": current["context"]["last_data_date"],
            },
        }
    )
    return result
