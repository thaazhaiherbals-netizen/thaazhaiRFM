"""Manual / historical Meta Insights sync. Read-only against Meta; never scheduled here.

Examples (local):
    python -m db.import_meta_insights --recent
    python -m db.import_meta_insights --from 2026-01-01 --to 2026-03-31 --async
"""

import argparse
from datetime import date

from apps.api.config import get_settings
from apps.api.db import get_engine
from apps.api.integrations.meta.client import MetaClient
from apps.api.integrations.meta.sync import (
    MAX_RANGE_DAYS,
    account_today,
    chunks,
    recent_window,
    run_sync,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    window = parser.add_mutually_exclusive_group(required=True)
    window.add_argument("--recent", action="store_true",
                        help="Re-fetch META_SYNC_LOOKBACK_DAYS through yesterday (account tz)")
    window.add_argument("--from", dest="date_from", type=date.fromisoformat)
    parser.add_argument("--to", dest="date_to", type=date.fromisoformat)
    parser.add_argument("--chunk-days", type=int, default=31,
                        help=f"Days per run for backfills (max {MAX_RANGE_DAYS})")
    parser.add_argument("--async", dest="use_async", action="store_true",
                        help="Use Meta's async report-run flow (large/historical ranges)")
    parser.add_argument("--trigger", choices=["MANUAL", "SCHEDULED", "BACKFILL"])
    args = parser.parse_args()

    settings = get_settings()
    if not settings.meta_configured:
        raise SystemExit("Meta is not configured: set META_AD_ACCOUNT_ID, META_ACCESS_TOKEN "
                         "and META_GRAPH_API_VERSION")
    if not 1 <= args.chunk_days <= MAX_RANGE_DAYS:
        raise SystemExit(f"--chunk-days must be between 1 and {MAX_RANGE_DAYS}")

    client = MetaClient(
        settings.meta_ad_account_id,
        settings.meta_access_token.get_secret_value(),
        settings.meta_graph_api_version,
    )
    try:
        if args.recent:
            account = client.get_account()
            today = account_today(
                account.get("timezone_name"), account.get("timezone_offset_hours_utc")
            )
            date_from, date_to = recent_window(settings.meta_sync_lookback_days, today)
            trigger = args.trigger or "MANUAL"
        else:
            if args.date_to is None:
                parser.error("--to is required with --from")
            date_from, date_to = args.date_from, args.date_to
            if settings.meta_sync_start_date and date_from < settings.meta_sync_start_date:
                raise SystemExit("--from is earlier than META_SYNC_START_DATE")
            trigger = args.trigger or "BACKFILL"
        for start, end in chunks(date_from, date_to, args.chunk_days):
            run_id = run_sync(
                get_engine(), client,
                ad_account_id=settings.meta_ad_account_id,
                api_version=settings.meta_graph_api_version,
                date_from=start, date_to=end,
                windows=settings.meta_attribution_windows,
                report_time=settings.meta_action_report_time,
                trigger=trigger, use_async=args.use_async,
            )
            print(f"Synced {start}..{end} run={run_id}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
