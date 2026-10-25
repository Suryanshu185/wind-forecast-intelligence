"""Elexon Insights API client for FUELHH and WINDFOR streaming endpoints.

Verified behaviour (docs/planning/04-data-research-notes.md): unauthenticated; stream endpoints return
a bare JSON array; WINDFOR can only be filtered by publish time; 400 for malformed parameters; 429 and
5xx are retryable. Ingestion is an offline/explicit operation, never a per-request call.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx

log = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_BACKOFF_SECONDS = 30.0


class ElexonError(Exception):
    """Base class for ingestion failures."""


class ElexonHTTPError(ElexonError):
    def __init__(self, status_code: int, url: str, body: str) -> None:
        super().__init__(f"Elexon API returned HTTP {status_code} for {url}: {body[:300]}")
        self.status_code = status_code
        self.url = url
        self.body = body


class ElexonTimeoutError(ElexonError):
    """Request timed out / transport failed after all retries."""


class ElexonSchemaError(ElexonError):
    """Response was not the expected JSON array of objects."""


@dataclass(frozen=True, slots=True)
class RequestRecord:
    """Provenance of one API request."""

    dataset: str
    endpoint: str
    query: dict[str, str]
    url: str
    retrieved_at: datetime
    status: int
    row_count: int
    attempts: int


@dataclass(frozen=True, slots=True)
class FetchResult:
    rows: list[dict[str, Any]]
    request: RequestRecord


def _iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("naive datetime not allowed")
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ElexonClient:
    def __init__(
        self,
        base_url: str = "https://data.elexon.co.uk/bmrs/api/v1",
        *,
        timeout: float = 60.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": "wind-forecast-intelligence/0.1"},
        )
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep
        self._clock = clock

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ElexonClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------ public API
    def fetch_fuelhh_wind(self, date_from: date, date_to: date) -> FetchResult:
        """FUELHH rows for WIND by settlement date (inclusive)."""
        params = {
            "settlementDateFrom": date_from.isoformat(),
            "settlementDateTo": date_to.isoformat(),
            "fuelType": "WIND",
        }
        return self._get_rows("FUELHH", "/datasets/FUELHH/stream", params)

    def fetch_windfor(self, publish_from: datetime, publish_to: datetime) -> FetchResult:
        """WINDFOR rows by *publish* time window (the dataset has no delivery-time filter)."""
        params = {
            "publishDateTimeFrom": _iso_z(publish_from),
            "publishDateTimeTo": _iso_z(publish_to),
        }
        return self._get_rows("WINDFOR", "/datasets/WINDFOR/stream", params)

    # ------------------------------------------------------------------ internals
    def _delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), MAX_BACKOFF_SECONDS)
            except ValueError:
                pass
        return min(self._backoff_base * (2**attempt), MAX_BACKOFF_SECONDS)

    def _get_rows(self, dataset: str, path: str, params: dict[str, str]) -> FetchResult:
        attempts = 0
        last_error: Exception | None = None
        while attempts <= self._max_retries:
            attempts += 1
            try:
                resp = self._client.get(path, params=params)
            except httpx.TransportError as exc:  # includes timeouts / connection errors
                last_error = exc
                log.warning("Elexon transport error (attempt %d): %s", attempts, exc)
                if attempts > self._max_retries:
                    break
                self._sleep(self._delay(attempts - 1, None))
                continue

            if resp.status_code in RETRYABLE_STATUS:
                last_error = ElexonHTTPError(resp.status_code, str(resp.url), resp.text)
                log.warning("Elexon HTTP %s (attempt %d)", resp.status_code, attempts)
                if attempts > self._max_retries:
                    raise last_error
                self._sleep(self._delay(attempts - 1, resp.headers.get("Retry-After")))
                continue
            if resp.status_code != 200:
                raise ElexonHTTPError(resp.status_code, str(resp.url), resp.text)

            try:
                payload = resp.json()
            except ValueError as exc:
                raise ElexonSchemaError(f"{dataset}: response is not valid JSON ({exc})") from exc
            if not isinstance(payload, list) or not all(isinstance(r, dict) for r in payload):
                raise ElexonSchemaError(f"{dataset}: expected a JSON array of objects")
            record = RequestRecord(
                dataset=dataset,
                endpoint=path,
                query=dict(params),
                url=str(resp.url),
                retrieved_at=self._clock(),
                status=resp.status_code,
                row_count=len(payload),
                attempts=attempts,
            )
            return FetchResult(rows=payload, request=record)

        raise ElexonTimeoutError(f"{dataset}: failed after {attempts} attempts: {last_error}")
