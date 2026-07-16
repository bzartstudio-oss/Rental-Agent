"""Tests for `discovery.automatic.capability` — the 14-capability heuristic
estimator. Every estimate must be honestly marked `is_estimate=True`.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.discovery.automatic.capability import estimate_capabilities

_NOW = datetime.now(timezone.utc)
_EXPECTED_KEYS = {
    "images", "prices", "availability", "coordinates", "addresses", "descriptions",
    "property_types", "room_sharing", "pagination", "search_filters", "saved_searches",
    "api_or_feed", "requires_javascript", "requires_login", "likely_connector_complexity",
}


class EstimateCapabilitiesTests(unittest.TestCase):
    def test_returns_all_fifteen_capability_keys(self) -> None:
        estimates = estimate_capabilities("c1", None, "unknown", now=_NOW)
        self.assertEqual({e.capability_key for e in estimates}, _EXPECTED_KEYS)

    def test_every_estimate_is_marked_as_estimate(self) -> None:
        estimates = estimate_capabilities("c1", "<html>apartment for rent, $1200/mo</html>", "no_login_required", now=_NOW)
        self.assertTrue(all(e.is_estimate for e in estimates))

    def test_no_body_yields_honest_unknown_not_a_guess(self) -> None:
        estimates = estimate_capabilities("c1", None, "unknown", now=_NOW)
        images = next(e for e in estimates if e.capability_key == "images")
        self.assertIsNone(images.estimated_value["present"])
        complexity = next(e for e in estimates if e.capability_key == "likely_connector_complexity")
        self.assertEqual(complexity.estimated_value["level"], "unknown")

    def test_price_markers_detected_from_body(self) -> None:
        estimates = estimate_capabilities("c1", "<html>Rent: $1500/mo, great price</html>", "no_login_required", now=_NOW)
        prices = next(e for e in estimates if e.capability_key == "prices")
        self.assertTrue(prices.estimated_value["present"])

    def test_requires_login_reuses_the_passed_in_verification_result_not_a_new_guess(self) -> None:
        estimates = estimate_capabilities("c1", "<html>no markers here</html>", "login_required", now=_NOW)
        login = next(e for e in estimates if e.capability_key == "requires_login")
        self.assertEqual(login.estimated_value["login_requirement"], "login_required")

    def test_api_or_feed_and_no_javascript_and_no_login_is_low_complexity(self) -> None:
        estimates = estimate_capabilities("c1", "<html>Our /api and rss feed are public</html>", "no_login_required", now=_NOW)
        complexity = next(e for e in estimates if e.capability_key == "likely_connector_complexity")
        self.assertEqual(complexity.estimated_value["level"], "low")

    def test_javascript_and_login_together_is_high_complexity(self) -> None:
        estimates = estimate_capabilities("c1", "<html><noscript>enable JS</noscript>React app</html>", "login_required", now=_NOW)
        complexity = next(e for e in estimates if e.capability_key == "likely_connector_complexity")
        self.assertEqual(complexity.estimated_value["level"], "high")


if __name__ == "__main__":
    unittest.main()
