from datetime import datetime, time, timedelta, timezone

from apps.api.integrations.meta.schedule import RunSummary, account_zone, decide

IST = timezone(timedelta(hours=5, minutes=30))
SIX = time(6, 0)


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 23, hour, minute, tzinfo=IST)


def test_waits_until_sync_time_then_runs():
    assert decide(at(5, 59), SIX, []) == "wait"
    assert decide(at(6, 0), SIX, []) == "run"


def test_catches_up_when_host_was_off_at_sync_time():
    assert decide(at(14, 30), SIX, []) == "run"


def test_never_repeats_a_successful_day():
    assert decide(at(9), SIX, [RunSummary("SUCCEEDED", at(6, 1))]) == "done"
    assert decide(at(9), SIX, [
        RunSummary("FAILED", at(6, 1)), RunSummary("SUCCEEDED", at(6, 40)),
    ]) == "done"


def test_failed_attempts_back_off_then_retry_then_give_up():
    one_failure = [RunSummary("FAILED", at(6, 1))]
    assert decide(at(6, 20), SIX, one_failure) == "backoff"
    assert decide(at(6, 31), SIX, one_failure) == "run"
    three = [RunSummary("FAILED", at(6, 1)), RunSummary("FAILED", at(6, 40)),
             RunSummary("FAILED", at(7, 20))]
    assert decide(at(12), SIX, three) == "gave_up"


def test_account_zone_falls_back_to_offset_then_utc():
    assert str(account_zone("Asia/Kolkata")) == "Asia/Kolkata"
    assert account_zone("Not/AZone", 5.5).utcoffset(None) == timedelta(hours=5, minutes=30)
    assert account_zone(None, None) == timezone.utc
