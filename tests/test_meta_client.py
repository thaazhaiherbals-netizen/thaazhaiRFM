import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from apps.api.integrations.meta.client import MetaApiError, MetaClient

FIXTURES = Path(__file__).parent / "fixtures" / "meta"
TOKEN = "fixture-secret-token-do-not-log"
WINDOWS = ["1d_view", "7d_click"]


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_client(handler, sleeps=None, **kwargs) -> MetaClient:
    return MetaClient(
        "1111111111", TOKEN, "v23.0",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=(sleeps.append if sleeps is not None else lambda _: None),
        **kwargs,
    )


def test_pagination_retrieves_every_page_once_without_token_in_url():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        after = request.url.params.get("after")
        page = {None: "insights_page_1.json", "AFTER1": "insights_page_2.json"}[after]
        return httpx.Response(200, json=fixture(page))

    client = make_client(handler)
    pages = list(
        client.iter_insight_pages(date(2026, 9, 1), date(2026, 9, 2), WINDOWS, "conversion")
    )
    assert [len(p) for p in pages] == [2, 1]
    assert len(seen) == 2
    for request in seen:
        assert TOKEN not in str(request.url)
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert request.url.path == "/v23.0/act_1111111111/insights"
        assert request.url.params["level"] == "ad"
        assert request.url.params["time_increment"] == "1"
        assert json.loads(request.url.params["time_range"]) == {
            "since": "2026-09-01", "until": "2026-09-02"
        }
        assert json.loads(request.url.params["action_attribution_windows"]) == WINDOWS


def test_transient_failures_retry_with_bounded_backoff_and_retry_after():
    responses = iter([
        httpx.Response(503),
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(400, json={"error": {"code": 17, "message": "User request limit"}}),
        httpx.Response(200, json={"data": []}, headers={"x-ad-account-usage": '{"acc":5}'}),
    ])
    sleeps: list[float] = []
    client = make_client(lambda request: next(responses), sleeps)
    day = date(2026, 9, 1)
    assert list(client.iter_insight_pages(day, day, WINDOWS, "conversion")) == [[]]
    assert sleeps == [1, 7, 4]
    assert client.attempts == 4
    assert client.usage == {"x-ad-account-usage": '{"acc":5}'}


def test_retries_are_bounded():
    sleeps: list[float] = []
    client = make_client(lambda request: httpx.Response(500), sleeps, max_attempts=3)
    with pytest.raises(MetaApiError, match="Gave up after 3 attempts"):
        client.get_account()
    assert len(sleeps) == 2


def test_permanent_error_fails_immediately_and_is_sanitized():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400, json={"error": {
            "code": 190, "message": f"Invalid OAuth access token {TOKEN}", "fbtrace_id": "abc",
        }})

    client = make_client(handler)
    with pytest.raises(MetaApiError) as caught:
        client.get_account()
    assert len(calls) == 1
    assert TOKEN not in str(caught.value)
    assert "[redacted]" in str(caught.value)
    assert caught.value.code == 190


def test_network_errors_retry_then_fail_without_token():
    def handler(request):
        raise httpx.ConnectError(f"boom {TOKEN}")

    client = make_client(handler, max_attempts=2)
    with pytest.raises(MetaApiError) as caught:
        client.get_account()
    assert TOKEN not in str(caught.value)


def test_async_report_polls_then_paginates():
    polls = iter(["Job Running", "Job Completed"])

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST":
            assert path.endswith("/act_1111111111/insights")
            return httpx.Response(200, json={"report_run_id": "9001"})
        if path == "/v23.0/9001":
            return httpx.Response(200, json={"async_status": next(polls)})
        assert path == "/v23.0/9001/insights"
        after = request.url.params.get("after")
        page = {None: "insights_page_1.json", "AFTER1": "insights_page_2.json"}[after]
        return httpx.Response(200, json=fixture(page))

    sleeps: list[float] = []
    client = make_client(handler, sleeps)
    pages = list(client.iter_async_insight_pages(
        date(2026, 1, 1), date(2026, 3, 31), WINDOWS, "conversion", poll_seconds=2,
    ))
    assert [len(p) for p in pages] == [2, 1]
    assert sleeps == [2]


def test_async_report_failure_is_reported():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"report_run_id": "9002"})
        return httpx.Response(200, json={"async_status": "Job Failed"})

    with pytest.raises(MetaApiError, match="Job Failed"):
        list(make_client(handler).iter_async_insight_pages(
            date(2026, 1, 1), date(2026, 1, 2), WINDOWS, "conversion"
        ))


def test_account_control_total_uses_account_level():
    def handler(request):
        assert request.url.params["level"] == "account"
        assert "time_increment" not in request.url.params
        return httpx.Response(200, json={"data": [{"spend": "1751.49"}]})

    assert make_client(handler).account_spend(
        date(2026, 9, 1), date(2026, 9, 2), WINDOWS, "conversion"
    ) == "1751.49"
