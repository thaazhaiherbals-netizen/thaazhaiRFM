"""Pure parsing of Meta Insights rows. No HTTP, no SQL.

Meta returns numbers as strings and reports overlapping action types for one event
(for example ``omni_purchase`` and ``offsite_conversion.fb_pixel_purchase``). Each
metric therefore takes the FIRST present type from a priority list instead of summing,
which would double count. Everything else remains in the raw arrays and is reported as
unclassified so new action types are never discarded.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

# Candidates in priority order. Confirm against a real account response before
# reconciliation (docs/META_MARKETING_INTEGRATION.md owner input 6).
DEFAULT_ACTION_TYPES: dict[str, tuple[str, ...]] = {
    "link_clicks": ("link_click",),
    "landing_page_views": ("landing_page_view", "omni_landing_page_view"),
    "add_to_cart": (
        "omni_add_to_cart", "add_to_cart", "offsite_conversion.fb_pixel_add_to_cart",
    ),
    # Confirmed on the live account 2026-09-23: "initiate_checkout" (no "d").
    "checkouts_initiated": (
        "omni_initiated_checkout", "initiate_checkout",
        "offsite_conversion.fb_pixel_initiate_checkout",
    ),
    "purchases": ("omni_purchase", "purchase", "offsite_conversion.fb_pixel_purchase"),
    "leads": ("lead", "onsite_conversion.lead_grouped", "offsite_conversion.fb_pixel_lead"),
}

REQUIRED_FIELDS = ("account_id", "campaign_id", "adset_id", "ad_id", "date_start", "date_stop")


class MetaParseError(ValueError):
    """A row cannot be normalized safely; the raw payload is still preserved."""


def to_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, float):
        value = repr(value)
    try:
        result = Decimal(str(value).strip())
    except InvalidOperation:
        raise MetaParseError(f"Not a number: {str(value)[:40]!r}") from None
    if not result.is_finite():
        raise MetaParseError("Number must be finite")
    return result


def to_int(value: object) -> int | None:
    number = to_decimal(value)
    if number is None:
        return None
    if number != number.to_integral_value():
        raise MetaParseError(f"Not a whole number: {number}")
    return int(number)


def action_totals(items: object) -> dict[str, Decimal]:
    """Map action_type -> ``value`` (the total for the requested attribution windows)."""
    if items is None:
        return {}
    if not isinstance(items, list):
        raise MetaParseError("Action list must be an array")
    totals: dict[str, Decimal] = {}
    for item in items:
        if not isinstance(item, dict) or not item.get("action_type"):
            raise MetaParseError("Action entry needs action_type")
        amount = to_decimal(item.get("value")) or Decimal(0)
        totals[item["action_type"]] = totals.get(item["action_type"], Decimal(0)) + amount
    return totals


def pick(totals: dict[str, Decimal], candidates: tuple[str, ...]) -> Decimal:
    for action_type in candidates:
        if action_type in totals:
            return totals[action_type]
    return Decimal(0)


@dataclass(frozen=True)
class ParsedInsight:
    ad_account_id: str
    campaign_id: str
    campaign_name: str | None
    objective: str | None
    ad_set_id: str
    ad_set_name: str | None
    ad_id: str
    ad_name: str | None
    reporting_date: date
    currency: str | None
    spend: Decimal
    impressions: int
    reach: int | None
    clicks: int
    link_clicks: int
    outbound_clicks: int
    landing_page_views: int
    add_to_cart: Decimal
    checkouts_initiated: Decimal
    purchases: Decimal
    purchase_value: Decimal
    leads: Decimal
    actions: list = field(default_factory=list)
    action_values: list = field(default_factory=list)
    unclassified_action_types: list[str] = field(default_factory=list)


def parse_insight_row(
    row: dict, action_types: dict[str, tuple[str, ...]] = DEFAULT_ACTION_TYPES
) -> ParsedInsight:
    missing = [name for name in REQUIRED_FIELDS if not row.get(name)]
    if missing:
        raise MetaParseError(f"Insight row missing {', '.join(missing)}")
    try:
        start = date.fromisoformat(row["date_start"])
        stop = date.fromisoformat(row["date_stop"])
    except (TypeError, ValueError):
        raise MetaParseError("Insight row has an invalid date") from None
    if start != stop:
        raise MetaParseError("Insight row must cover one day (time_increment=1)")

    actions = action_totals(row.get("actions"))
    values = action_totals(row.get("action_values"))
    outbound = action_totals(row.get("outbound_clicks"))
    known = {name for candidates in action_types.values() for name in candidates}
    spend = to_decimal(row.get("spend")) or Decimal(0)
    link_clicks = to_int(row.get("inline_link_clicks"))
    if link_clicks is None:
        link_clicks = int(pick(actions, action_types["link_clicks"]))

    return ParsedInsight(
        ad_account_id=str(row["account_id"]).removeprefix("act_"),
        campaign_id=str(row["campaign_id"]),
        campaign_name=row.get("campaign_name"),
        objective=row.get("objective"),
        ad_set_id=str(row["adset_id"]),
        ad_set_name=row.get("adset_name"),
        ad_id=str(row["ad_id"]),
        ad_name=row.get("ad_name"),
        reporting_date=start,
        currency=row.get("account_currency"),
        spend=spend.quantize(Decimal("0.01")),
        impressions=to_int(row.get("impressions")) or 0,
        reach=to_int(row.get("reach")),
        clicks=to_int(row.get("clicks")) or 0,
        link_clicks=link_clicks,
        outbound_clicks=int(outbound.get("outbound_click", Decimal(0))),
        landing_page_views=int(pick(actions, action_types["landing_page_views"])),
        add_to_cart=pick(actions, action_types["add_to_cart"]),
        checkouts_initiated=pick(actions, action_types["checkouts_initiated"]),
        purchases=pick(actions, action_types["purchases"]),
        purchase_value=pick(values, action_types["purchases"]).quantize(Decimal("0.01")),
        leads=pick(actions, action_types["leads"]),
        actions=row.get("actions") or [],
        action_values=row.get("action_values") or [],
        unclassified_action_types=sorted(set(actions) - known),
    )
