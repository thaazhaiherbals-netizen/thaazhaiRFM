"""Resolve confirmed aliases; never create or guess product mappings."""

from uuid import UUID

from sqlalchemy import Connection, text

from apps.api.normalization import OrderValidationError, normalize_text


class MappingPending(OrderValidationError):
    """Catalogue correction is needed, but the sale can still be saved."""


def resolve_product(
    connection: Connection, source: str, name: str, variant: str | None
) -> tuple[UUID, UUID | None]:
    # V1 catalogue is small. Normalize stored aliases in Python too, so HTML
    # entities and old normalized_alias conventions cannot hide real matches.
    aliases = connection.execute(
        text("""
        SELECT a.product_id, a.variant_id, a.alias_name, a.alias_variant,
               p.active AS product_active, v.active AS variant_active,
               v.product_id AS variant_product_id
        FROM product_aliases a
        JOIN products p ON p.id = a.product_id
        LEFT JOIN product_variants v ON v.id = a.variant_id
        WHERE a.active AND a.source_system = :source
    """),
        {"source": source},
    ).mappings()
    matches = [
        row
        for row in aliases
        if normalize_text(row["alias_name"]) == normalize_text(name)
        and normalize_text(row["alias_variant"]) == normalize_text(variant)
    ]
    label = f"{name!r} / {variant!r}"
    if not matches:
        raise MappingPending(f"Unmapped product: {label}")
    if len(matches) != 1:
        raise MappingPending(f"Ambiguous product mapping: {label}")
    match = matches[0]
    if not match["product_active"] or (
        match["variant_id"]
        and (not match["variant_active"] or match["variant_product_id"] != match["product_id"])
    ):
        raise MappingPending(f"Inactive or inconsistent product mapping: {label}")
    return match["product_id"], match["variant_id"]
