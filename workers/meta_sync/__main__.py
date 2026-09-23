"""Daily Meta Ads sync scheduler. Run with python -m workers.meta_sync.

Separate from the order worker (docs/META_MARKETING_INTEGRATION.md). Checks every few
minutes and syncs once per day after META_SYNC_TIME in the ad account's timezone.
Idles harmlessly when Meta is not configured.
"""

import logging
import signal
from threading import Event

from apps.api.config import get_settings
from apps.api.db import get_engine
from apps.api.integrations.meta.client import MetaClient
from apps.api.integrations.meta.schedule import run_scheduled_once

POLL_SECONDS = 300
stopping = Event()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("thaazhai.meta_scheduler")
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    settings = get_settings()
    engine = get_engine()
    if not settings.meta_configured:
        log.warning('{"event":"meta_scheduler_idle","reason":"meta_not_configured"}')

    def client() -> MetaClient:
        return MetaClient(
            settings.meta_ad_account_id,
            settings.meta_access_token.get_secret_value(),
            settings.meta_graph_api_version,
        )

    try:
        while not stopping.is_set():
            if settings.meta_configured:
                try:
                    decision = run_scheduled_once(engine, settings, client)
                    log.info('{"event":"meta_scheduler_tick","decision":"%s"}', decision)
                except Exception as error:
                    log.error('{"event":"meta_scheduler_tick_failed","type":"%s"}',
                              type(error).__name__)
            stopping.wait(POLL_SECONDS)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
