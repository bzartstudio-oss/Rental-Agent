"""Tests for `discovery.automatic.verification` — "Do not use uncontrolled
scraping in tests" (the mission's own words): every test here injects a fake
`PageFetcher`, never `HttpPageFetcher`/a real network call.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.discovery.automatic.verification import (
    PageFetchResult,
    verify_domain_accessibility,
    verify_homepage_content,
)

_NOW = datetime.now(timezone.utc)


class _FakeFetcher:
    def __init__(self, result: PageFetchResult) -> None:
        self._result = result

    def fetch(self, url: str) -> PageFetchResult:
        return self._result


class VerifyDomainAccessibilityTests(unittest.TestCase):
    def test_2xx_status_is_a_pass(self) -> None:
        fetcher = _FakeFetcher(PageFetchResult(status_code=200, body="<html></html>", final_url="https://example.com"))
        result = verify_domain_accessibility("c1", "https://example.com", fetcher, now=_NOW)
        self.assertEqual(result.result, "pass")
        self.assertEqual(result.check_type, "domain_accessibility")

    def test_network_error_is_an_honest_fail_not_an_exception(self) -> None:
        fetcher = _FakeFetcher(PageFetchResult(status_code=None, body=None, final_url=None, error="timed out"))
        result = verify_domain_accessibility("c1", "https://example.com", fetcher, now=_NOW)
        self.assertEqual(result.result, "fail")
        self.assertEqual(result.detail["error"], "timed out")

    def test_4xx_status_is_a_fail(self) -> None:
        fetcher = _FakeFetcher(PageFetchResult(status_code=404, body=None, final_url="https://example.com/missing"))
        result = verify_domain_accessibility("c1", "https://example.com", fetcher, now=_NOW)
        self.assertEqual(result.result, "fail")


class VerifyHomepageContentTests(unittest.TestCase):
    def test_no_body_yields_honest_unknown_for_both_checks(self) -> None:
        results = verify_homepage_content("c1", PageFetchResult(status_code=None, body=None, final_url=None, error="x"), now=_NOW)
        self.assertEqual({r.check_type: r.result for r in results}, {
            "listing_or_search_page_presence": "unknown", "login_requirement": "unknown",
        })

    def test_listing_markers_present_is_a_pass(self) -> None:
        body = "<html>Browse our apartment and room listings for rent</html>"
        results = verify_homepage_content("c1", PageFetchResult(status_code=200, body=body, final_url="https://x.com"), now=_NOW)
        presence = next(r for r in results if r.check_type == "listing_or_search_page_presence")
        self.assertEqual(presence.result, "pass")

    def test_no_listing_markers_is_a_fail(self) -> None:
        body = "<html>Welcome to our totally unrelated cooking blog</html>"
        results = verify_homepage_content("c1", PageFetchResult(status_code=200, body=body, final_url="https://x.com"), now=_NOW)
        presence = next(r for r in results if r.check_type == "listing_or_search_page_presence")
        self.assertEqual(presence.result, "fail")

    def test_login_markers_present_is_login_required_not_pass_fail(self) -> None:
        body = "<html>Please log in or sign up to continue</html>"
        results = verify_homepage_content("c1", PageFetchResult(status_code=200, body=body, final_url="https://x.com"), now=_NOW)
        login = next(r for r in results if r.check_type == "login_requirement")
        self.assertEqual(login.result, "login_required")

    def test_no_login_markers_is_no_login_required(self) -> None:
        body = "<html>Browse apartments for rent, no account needed</html>"
        results = verify_homepage_content("c1", PageFetchResult(status_code=200, body=body, final_url="https://x.com"), now=_NOW)
        login = next(r for r in results if r.check_type == "login_requirement")
        self.assertEqual(login.result, "no_login_required")


if __name__ == "__main__":
    unittest.main()
