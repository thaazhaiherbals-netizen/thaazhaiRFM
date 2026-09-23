"""Read-only Meta Graph API client: pagination, async reports, bounded retries.

The access token travels only in the Authorization header. Pagination re-issues the
original request with the ``after`` cursor instead of following ``paging.next``
(which embeds ``access_token`` in its URL). Every error message is scrubbed of the
token before it can reach logs, exceptions or the database.
"""

import json
import time
from collections.abc import Callable, Iterator
from datetime import date

import httpx

GRAPH_URL = "https://graph.facebook.com"

INSIGHT_FIELDS = (
    "account_id", "account_name", "account_currency",
    "campaign_id", "campaign_name", "objective",
    "adset_id", "adset_name", "ad_id", "ad_name",
    "spend", "impressions", "reach", "frequency", "clicks",
    "inline_link_clicks", "outbound_clicks", "actions", "action_values",
    "date_start", "date_stop",
)
ACCOUNT_FIELDS = ("account_id", "name", "currency", "timezone_name", "timezone_offset_hours_utc")
USAGE_HEADERS = (
    "x-business-use-case-usage", "x-ad-account-usage", "x-app-usage",
    "x-fb-ads-insights-throttle",
)
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
# Meta rate-limit/throttle error codes that are safe to retry.
RETRY_CODES = frozenset({1, 2, 4, 17, 32, 341, 613, 80000, 80003, 80004, 80014})


class MetaApiError(RuntimeError):
    """A sanitized, permanent (or retry-exhausted) Meta API failure."""

    def __init__(self, message: str, status: int | None = None, code: int | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


class MetaClient:
    def __init__(
        self,
        ad_account_id: str,
        access_token: str,
        api_version: str,
        *,
        http: httpx.Client | None = None,
        max_attempts: int = 5,
        max_backoff_seconds: float = 60,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not (ad_account_id and access_token and api_version):
            raise ValueError("Meta client needs an account, token and API version")
        self.account = f"act_{ad_account_id.removeprefix('act_')}"
        self._token = access_token
        self._base = f"{GRAPH_URL}/{api_version}"
        self._http = http or httpx.Client(timeout=httpx.Timeout(60, connect=10))
        self._max_attempts = max_attempts
        self._max_backoff = max_backoff_seconds
        self._sleep = sleep
        self.attempts = 0
        self.usage: dict[str, str] = {}

    def close(self) -> None:
        self._http.close()

    def _scrub(self, text: str) -> str:
        return text.replace(self._token, "[redacted]")[:500]

    def _request(self, method: str, path: str, params: dict) -> dict:
        headers = {"Authorization": f"Bearer {self._token}"}
        for attempt in range(1, self._max_attempts + 1):
            self.attempts += 1
            retry_after: float | None = None
            try:
                response = self._http.request(
                    method, f"{self._base}/{path}", params=params, headers=headers
                )
            except httpx.TransportError as error:
                failure = MetaApiError(self._scrub(f"Network error: {type(error).__name__}"))
            else:
                self.usage.update(
                    {k: response.headers[k] for k in USAGE_HEADERS if k in response.headers}
                )
                if response.is_success:
                    return response.json()
                failure = self._error(response)
                if not self._retryable(response, failure):
                    raise failure
                retry_after = _retry_after(response)
            if attempt == self._max_attempts:
                raise MetaApiError(
                    f"Gave up after {attempt} attempts: {failure}", failure.status, failure.code
                )
            self._sleep(retry_after or min(self._max_backoff, 2 ** (attempt - 1)))
        raise AssertionError("unreachable")

    def _error(self, response: httpx.Response) -> MetaApiError:
        try:
            body = response.json().get("error", {})
        except ValueError:
            body = {}
        code = body.get("code")
        parts = [f"HTTP {response.status_code}"]
        if code is not None:
            parts.append(f"code {code}")
        if body.get("error_subcode"):
            parts.append(f"subcode {body['error_subcode']}")
        if body.get("message"):
            parts.append(str(body["message"]))
        if body.get("fbtrace_id"):
            parts.append(f"fbtrace {body['fbtrace_id']}")
        return MetaApiError(self._scrub(" | ".join(parts)), response.status_code, code)

    @staticmethod
    def _retryable(response: httpx.Response, failure: MetaApiError) -> bool:
        if response.status_code in RETRY_STATUS or failure.code in RETRY_CODES:
            return True
        try:
            return bool(response.json().get("error", {}).get("is_transient"))
        except ValueError:
            return False

    def get_account(self) -> dict:
        return self._request("GET", self.account, {"fields": ",".join(ACCOUNT_FIELDS)})

    def _insight_params(
        self, date_from: date, date_to: date, windows: list[str], report_time: str,
        level: str = "ad", time_increment: int | None = 1,
    ) -> dict:
        params = {
            "level": level,
            "fields": ",".join(INSIGHT_FIELDS if level == "ad" else ("spend",)),
            "time_range": json.dumps(
                {"since": date_from.isoformat(), "until": date_to.isoformat()}
            ),
            "action_attribution_windows": json.dumps(windows),
            "action_report_time": report_time,
            "limit": 500,
        }
        if time_increment:
            params["time_increment"] = time_increment
        return params

    def _pages(self, path: str, params: dict) -> Iterator[list[dict]]:
        after: str | None = None
        while True:
            body = self._request("GET", path, {**params, **({"after": after} if after else {})})
            yield body.get("data", [])
            paging = body.get("paging") or {}
            after = (paging.get("cursors") or {}).get("after")
            if not paging.get("next") or not after:
                return

    def iter_insight_pages(
        self, date_from: date, date_to: date, windows: list[str], report_time: str
    ) -> Iterator[list[dict]]:
        """Synchronous Insights for small windows; yields one list of rows per page."""
        params = self._insight_params(date_from, date_to, windows, report_time)
        yield from self._pages(f"{self.account}/insights", params)

    def iter_async_insight_pages(
        self, date_from: date, date_to: date, windows: list[str], report_time: str,
        *, poll_seconds: float = 5, max_wait_seconds: float = 1800,
    ) -> Iterator[list[dict]]:
        """Report-run flow for historical/large ranges."""
        params = self._insight_params(date_from, date_to, windows, report_time)
        run_id = self._request("POST", f"{self.account}/insights", params).get("report_run_id")
        if not run_id:
            raise MetaApiError("Meta did not return a report_run_id")
        waited = 0.0
        while True:
            status = self._request(
                "GET", str(run_id), {"fields": "async_status,async_percent_completion"}
            )
            state = status.get("async_status")
            if state == "Job Completed":
                break
            if state in ("Job Failed", "Job Skipped"):
                raise MetaApiError(f"Async report ended with status {state}")
            if waited >= max_wait_seconds:
                raise MetaApiError("Async report did not finish in time")
            self._sleep(poll_seconds)
            waited += poll_seconds
        yield from self._pages(f"{run_id}/insights", {"limit": 500})

    def account_spend(
        self, date_from: date, date_to: date, windows: list[str], report_time: str
    ) -> str | None:
        """Account-level control total, stored separately from ad-level facts."""
        params = self._insight_params(
            date_from, date_to, windows, report_time, level="account", time_increment=None
        )
        rows = self._request("GET", f"{self.account}/insights", params).get("data", [])
        return rows[0].get("spend") if rows else "0"


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    try:
        return min(float(value), 300) if value else None
    except ValueError:
        return None
