"""Tests for `discovery.automatic.evidence_collection` — turning one discovered
URL + fetched homepage into the mission's 15 named evidence types.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.discovery.automatic.evidence_collection import collect_evidence, evidence_text_for_classification
from src.discovery.automatic.models import DiscoveredURL, DiscoveryRequest
from src.discovery.automatic.verification import PageFetchResult

_NOW = datetime.now(timezone.utc)


class CollectEvidenceTests(unittest.TestCase):
    def test_always_includes_discovered_url_and_provider(self) -> None:
        discovered = DiscoveredURL(url="https://example.com", name="Example")
        evidence = collect_evidence("c1", "r1", discovered, "curated_seed", None, DiscoveryRequest(), now=_NOW)
        types = {e.evidence_type for e in evidence}
        self.assertIn("discovered_url", types)
        self.assertIn("provider", types)
        self.assertTrue(all(e.discovery_provider == "curated_seed" for e in evidence))

    def test_no_fetch_result_still_records_robots_observation_honestly(self) -> None:
        discovered = DiscoveredURL(url="https://example.com")
        evidence = collect_evidence("c1", "r1", discovered, "manual_url", None, DiscoveryRequest(), now=_NOW)
        robots = next(e for e in evidence if e.evidence_type == "robots_or_policy_observation")
        self.assertFalse(robots.value["checked"])

    def test_page_title_and_description_extracted_when_body_present(self) -> None:
        body = '<html><head><title>Example Rentals</title><meta name="description" content="Find apartments"></head></html>'
        fetch_result = PageFetchResult(status_code=200, body=body, final_url="https://example.com")
        discovered = DiscoveredURL(url="https://example.com")
        evidence = collect_evidence("c1", "r1", discovered, "curated_seed", fetch_result, DiscoveryRequest(), now=_NOW)
        title = next(e for e in evidence if e.evidence_type == "page_title")
        description = next(e for e in evidence if e.evidence_type == "page_description")
        self.assertEqual(title.value["title"], "Example Rentals")
        self.assertEqual(description.value["description"], "Find apartments")

    def test_location_and_category_evidence_matched_from_body(self) -> None:
        body = "<html>Apartments for rent in Valencia, Spain</html>"
        fetch_result = PageFetchResult(status_code=200, body=body, final_url="https://example.com")
        discovered = DiscoveredURL(url="https://example.com")
        request = DiscoveryRequest(country="Spain", city="Valencia", rental_categories=["apartment"])
        evidence = collect_evidence("c1", "r1", discovered, "curated_seed", fetch_result, request, now=_NOW)
        location = next(e for e in evidence if e.evidence_type == "location_evidence")
        category = next(e for e in evidence if e.evidence_type == "rental_category_evidence")
        self.assertIn("Spain", location.value["matched_locations"])
        self.assertIn("Valencia", location.value["matched_locations"])
        self.assertIn("apartment", category.value["matched_categories"])

    def test_no_fabricated_evidence_when_nothing_matches(self) -> None:
        body = "<html>Completely unrelated content</html>"
        fetch_result = PageFetchResult(status_code=200, body=body, final_url="https://example.com")
        discovered = DiscoveredURL(url="https://example.com")
        request = DiscoveryRequest(country="Spain")
        evidence = collect_evidence("c1", "r1", discovered, "curated_seed", fetch_result, request, now=_NOW)
        self.assertFalse(any(e.evidence_type == "location_evidence" for e in evidence))


class EvidenceTextForClassificationTests(unittest.TestCase):
    def test_combines_name_source_hint_title_and_description(self) -> None:
        discovered = DiscoveredURL(url="https://example.com", name="Example", source_hint="curated_seed:manual_seed")
        body = '<html><head><title>Rentals</title><meta name="description" content="apartments"></head></html>'
        fetch_result = PageFetchResult(status_code=200, body=body, final_url="https://example.com")
        text = evidence_text_for_classification(discovered, fetch_result)
        self.assertIn("Example", text)
        self.assertIn("Rentals", text)
        self.assertIn("apartments", text)

    def test_handles_no_fetch_result(self) -> None:
        discovered = DiscoveredURL(url="https://example.com", name="Example")
        text = evidence_text_for_classification(discovered, None)
        self.assertIn("Example", text)


if __name__ == "__main__":
    unittest.main()
