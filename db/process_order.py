"""Process one explicitly selected LOCAL raw order."""

import argparse
from uuid import UUID

from apps.api.config import get_settings
from apps.api.db import get_engine
from apps.api.order_processing import process_single_order


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", type=UUID, required=True, help="raw_order_ingestion.id")
    parser.add_argument("--retry-error", action="store_true")
    args = parser.parse_args()
    if get_settings().app_env != "development":
        parser.error("This manual learning command runs only in development")
    result = process_single_order(get_engine(), args.id, retry_error=args.retry_error)
    print(f"Status: {result.status}")
    print(f"Items needing mapping: {result.pending_items}")
    if result.order_id:
        print(f"Order ID: {result.order_id}")
    if result.error:
        print(result.error)


if __name__ == "__main__":
    main()
