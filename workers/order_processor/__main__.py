"""Run with python -m workers.order_processor. Stop with Ctrl+C or SIGTERM."""

import logging
import signal
from threading import Event

from apps.api.db import get_engine
from apps.api.jobs import run_next_job

stopping = Event()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    engine = get_engine()
    try:
        while not stopping.is_set():
            try:
                run_next_job(engine)
            except Exception:
                logging.getLogger("thaazhai.worker").error('{"event":"worker_tick_failed"}')
            stopping.wait(2)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
