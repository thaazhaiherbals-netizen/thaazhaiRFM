"""Pure functions: no database access, so these are easy to learn and test."""

import html
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


class OrderValidationError(ValueError):
    """Expected business-data error; safe to show to an administrator."""


def normalize_text(value: str | None) -> str:
    return " ".join(html.unescape(value or "").split()).lower()


def normalize_phone(value: object) -> str:
    if not isinstance(value, str) or re.search(r"[^0-9+()\s-]", value):
        raise OrderValidationError("A valid Indian customer phone is required")
    digits = re.sub(r"[^0-9]", "", value)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise OrderValidationError("A valid Indian customer phone is required")
    return "+91" + digits


def parse_order_date(value: object) -> date:
    if not isinstance(value, str):
        raise OrderValidationError("order_date is required")
    for pattern in ("%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            pass
    raise OrderValidationError("order_date must be Month D, YYYY or YYYY-MM-DD")


def money(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise OrderValidationError(f"{field} must be a nonnegative money amount")
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount >= Decimal("10000000000"):
            raise ValueError
        if amount != amount.quantize(Decimal("0.01")):
            raise ValueError
    except (InvalidOperation, ValueError):
        raise OrderValidationError(f"{field} must fit NUMERIC(12,2)") from None
    return amount.quantize(Decimal("0.01"))


def required_text(value: object, field: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise OrderValidationError(f"{field} must be nonempty text up to {max_length} characters")
    return value


def optional_text(value: object, field: str, max_length: int) -> str | None:
    if value is None or value == "":
        return None
    return required_text(value, field, max_length)
