"""Verification — configurable, honest accessibility/relevance checks. See
docs/29_Automatic_Platform_Discovery.md "Verification".

Deliberately lightweight: one polite HTTP GET of the homepage, never a full
scrape, never a login attempt, never anything that could be mistaken for
bypassing a CAPTCHA/rate limit/robots restriction — "Do not bypass:
authentication, access controls, CAPTCHAs, rate limits, robots restrictions,
anti-bot protections" (the mission's own words). `PageFetcher` is an injectable
protocol specifically so every test in this codebase can supply a fixture/mock
response instead of making a real network call — "Do not use uncontrolled
scraping in tests" (the mission's own words).

"Verification failures must not erase a platform" (the mission's own words): every
function here returns a `PlatformVerificationResult`, never raises for an
ordinary failure (timeout, 404, connection refused) — those are honest `"fail"`
results, not exceptions.
"""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from urllib.error import URLError

from src.discovery.automatic.models import PlatformVerificationResult

_REQUEST_TIMEOUT_SECONDS = 8.0
_USER_AGENT = "RentalAgentDiscoveryBot/1.0 (+platform discovery, homepage check only)"


@dataclass
class PageFetchResult:
    status_code: int | None
    body: str | None
    final_url: str | None
    error: str | None = None


class PageFetcher(Protocol):
    def fetch(self, url: str) -> PageFetchResult: ...


class HttpPageFetcher:
    """The one real `PageFetcher` — a single, polite `GET` with a real timeout and
    an honest, identifying User-Agent. No retries, no JavaScript execution, no
    login attempt, no CAPTCHA solving.
    """

    def fetch(self, url: str) -> PageFetchResult:
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
                body = response.read(1_000_000).decode("utf-8", errors="replace")
                return PageFetchResult(status_code=response.status, body=body, final_url=response.geturl())
        except URLError as exc:
            return PageFetchResult(status_code=None, body=None, final_url=None, error=str(exc))
        except (TimeoutError, OSError, ValueError) as exc:
            return PageFetchResult(status_code=None, body=None, final_url=None, error=str(exc))


def verify_domain_accessibility(
    candidate_id: str, url: str, fetcher: PageFetcher, *, now: datetime | None = None
) -> PlatformVerificationResult:
    now = now or datetime.now(timezone.utc)
    result = fetcher.fetch(url)

    if result.error is not None:
        return PlatformVerificationResult(
            candidate_id=candidate_id, check_type="domain_accessibility", result="fail",
            detail={"error": result.error}, observed_at=now,
        )
    if result.status_code is not None and 200 <= result.status_code < 400:
        return PlatformVerificationResult(
            candidate_id=candidate_id, check_type="domain_accessibility", result="pass",
            detail={"status_code": result.status_code, "final_url": result.final_url}, observed_at=now,
        )
    return PlatformVerificationResult(
        candidate_id=candidate_id, check_type="domain_accessibility", result="fail",
        detail={"status_code": result.status_code}, observed_at=now,
    )


def verify_homepage_content(
    candidate_id: str, fetch_result: PageFetchResult, *, now: datetime | None = None
) -> list[PlatformVerificationResult]:
    """Cheap, honest keyword-presence checks against an already-fetched homepage
    body — never a second network call. `"unknown"` (never a fabricated
    `"pass"`/`"fail"`) when there's no body to inspect at all.
    """
    now = now or datetime.now(timezone.utc)
    results = []

    if fetch_result.body is None:
        for check_type in ("listing_or_search_page_presence", "login_requirement"):
            results.append(
                PlatformVerificationResult(candidate_id=candidate_id, check_type=check_type, result="unknown", observed_at=now)
            )
        return results

    body_lower = fetch_result.body.lower()

    listing_markers = ("apartment", "rent", "listing", "property", "room", "flat")
    has_listing_markers = any(marker in body_lower for marker in listing_markers)
    results.append(
        PlatformVerificationResult(
            candidate_id=candidate_id, check_type="listing_or_search_page_presence",
            result="pass" if has_listing_markers else "fail",
            detail={"matched_markers": [m for m in listing_markers if m in body_lower]}, observed_at=now,
        )
    )

    login_markers = ("log in", "login", "sign in", "sign up", "create account")
    requires_login = any(marker in body_lower for marker in login_markers)
    results.append(
        PlatformVerificationResult(
            candidate_id=candidate_id, check_type="login_requirement",
            # Deliberately not "pass"/"fail" for this one check — neither direction
            # reads unambiguously as success — so the result names the actual
            # finding instead.
            result="login_required" if requires_login else "no_login_required",
            detail={"matched_markers": [m for m in login_markers if m in body_lower]}, observed_at=now,
        )
    )

    return results
