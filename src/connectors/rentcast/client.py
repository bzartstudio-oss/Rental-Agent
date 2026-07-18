"""Thin HTTP wrapper around the real RentCast API (https://developers.rentcast.io) —
kept separate from `RentCastConnector` so retry/backoff/timeout policy (transport
concerns) never mixes with normalization policy (data-shape concerns). Uses `requests`
directly rather than `src.collectors.http_collector`: RentCast needs a custom header,
per-status retry rules, and immediate (non-retried) failure on 401 — more control than
`http_collector.fetch_json()`'s generic `raise_for_status()` gives.
"""

from __future__ import annotations

import time
from typing import Any

import requests

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Fixed, short backoff — RentCast's free tier (50 requests/month) makes an aggressive
# retry schedule actively harmful (it burns quota on a resource that's probably still
# down), so this favors a small number of well-spaced attempts over rapid retries.
_BACKOFF_BASE_SECONDS = 0.5

# A cap on how long a single `Retry-After` value is ever honored for. Without this, a
# misbehaving or malicious response could stall an entire search job — the same
# "never let one thing quietly hang the whole run" discipline `_MAX_PAGES` already
# applies to pagination.
_MAX_RETRY_AFTER_SECONDS = 60.0


class RentCastClientError(Exception):
    """Wraps every network/HTTP failure (timeout, connection error, 401, 5xx, or any
    other non-2xx response) into one exception type, so `RentCastConnector` never needs
    to know about `requests`'s own exception hierarchy or RentCast's status codes.
    """


class RentCastRateLimitError(RentCastClientError):
    """Raised when RentCast returns 429 and retries are exhausted. A subclass of
    `RentCastClientError` — every existing caller that catches the parent type (e.g.
    `RentCastConnector.fetch_listing()`) needs no change, while a caller that wants to
    distinguish "rate limited" from "some other failure" can catch this specifically.
    """


def _parse_retry_after(value: str | None) -> float | None:
    """RentCast's `Retry-After` (per RFC 7231) is an integer/float number of seconds in
    practice for rate-limit responses — the HTTP-date form is not handled (deliberately
    out of scope; falls back to exponential backoff exactly like a missing header
    would). Returns `None` for anything unparseable, never raises.
    """
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return max(0.0, min(seconds, _MAX_RETRY_AFTER_SECONDS))


class RentCastClient:
    BASE_URL = "https://api.rentcast.io/v1"
    RENTAL_LISTINGS_ENDPOINT = "/listings/rental/long-term"

    def __init__(self, api_key: str, timeout_ms: int = 30_000, max_retries: int = 0) -> None:
        self._api_key = api_key
        self._timeout_s = timeout_ms / 1000
        self._max_retries = max(0, max_retries)

    def get_rental_listings(self, params: dict[str, Any]) -> list[dict]:
        """One page of `GET /listings/rental/long-term`. Retries a connection error,
        timeout, or 5xx response up to `max_retries` times with exponential backoff.
        A 401 (missing/invalid API key) fails immediately without retrying — no number
        of retries turns a bad key into a good one.
        """
        return self._get(self.RENTAL_LISTINGS_ENDPOINT, params)

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{self.BASE_URL}{path}"
        attempt = 0

        while True:
            try:
                response = requests.get(
                    url,
                    headers={"X-Api-Key": self._api_key},
                    params=params,
                    timeout=self._timeout_s,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt >= self._max_retries:
                    raise RentCastClientError(
                        f"request to {path} failed after {attempt + 1} attempt(s): {exc}"
                    ) from exc
                logger.warning(
                    "rentcast request failed, retrying", extra={"path": path, "attempt": attempt + 1, "error": str(exc)}
                )
                time.sleep(_BACKOFF_BASE_SECONDS * (2**attempt))
                attempt += 1
                continue

            if response.status_code == 401:
                raise RentCastClientError(
                    f"authentication failed (401) on {path} — check the configured API key"
                )

            if response.status_code == 429:
                if attempt >= self._max_retries:
                    raise RentCastRateLimitError(
                        f"rate limit exceeded (429) on {path} after {attempt + 1} attempt(s)"
                    )
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                wait_seconds = retry_after if retry_after is not None else _BACKOFF_BASE_SECONDS * (2**attempt)
                # Never log headers or the API key — only path/attempt/timing, the same
                # discipline every other log line in this module already follows.
                logger.warning(
                    "rentcast rate limited, retrying",
                    extra={
                        "path": path,
                        "attempt": attempt + 1,
                        "wait_seconds": wait_seconds,
                        "retry_after_header_present": retry_after is not None,
                    },
                )
                time.sleep(wait_seconds)
                attempt += 1
                continue

            if response.status_code >= 500:
                if attempt >= self._max_retries:
                    raise RentCastClientError(
                        f"server error {response.status_code} on {path} after {attempt + 1} attempt(s)"
                    )
                logger.warning(
                    "rentcast server error, retrying",
                    extra={"path": path, "attempt": attempt + 1, "status_code": response.status_code},
                )
                time.sleep(_BACKOFF_BASE_SECONDS * (2**attempt))
                attempt += 1
                continue

            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise RentCastClientError(f"request to {path} was rejected: {exc}") from exc

            return response.json()
