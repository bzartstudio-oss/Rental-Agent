"""Tests for `discovery.automatic.normalization` — domain/name normalization and
the two duplicate-candidate lookups.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.discovery.automatic import normalization
from src.discovery.automatic.models import PlatformCandidate, PlatformClassification, PlatformStatus

_NOW = datetime.now(timezone.utc)


def _candidate(candidate_id: str, domain: str, name: str) -> PlatformCandidate:
    return PlatformCandidate(
        candidate_id=candidate_id, normalized_domain=domain, name=name, raw_url=f"https://{domain}",
        status=PlatformStatus.DISCOVERED, classification=PlatformClassification.UNKNOWN,
        first_discovered_at=_NOW, last_seen_at=_NOW, last_run_id="r1",
    )


class NormalizeDomainTests(unittest.TestCase):
    def test_strips_scheme_and_www_and_trailing_slash(self) -> None:
        self.assertEqual(normalization.normalize_domain("https://www.Example.com/"), "example.com")
        self.assertEqual(normalization.normalize_domain("http://example.com"), "example.com")

    def test_equivalent_urls_normalize_identically(self) -> None:
        self.assertEqual(
            normalization.normalize_domain("https://www.example.com/"),
            normalization.normalize_domain("example.com"),
        )

    def test_configured_alias_resolves_to_canonical_domain(self) -> None:
        normalization.DOMAIN_ALIASES["alias.example"] = "canonical.example"
        try:
            self.assertEqual(normalization.normalize_domain("https://alias.example"), "canonical.example")
        finally:
            normalization.DOMAIN_ALIASES.clear()


class NormalizeNameTests(unittest.TestCase):
    def test_case_and_whitespace_insensitive(self) -> None:
        self.assertEqual(normalization.normalize_name("  Example   Platform "), normalization.normalize_name("example platform"))


class FindDuplicateCandidateTests(unittest.TestCase):
    def test_matches_on_normalized_domain(self) -> None:
        existing = [_candidate("c1", "example.com", "Example")]
        match = normalization.find_duplicate_candidate(existing, "example.com")
        self.assertIsNotNone(match)
        self.assertEqual(match.candidate_id, "c1")

    def test_no_match_returns_none(self) -> None:
        existing = [_candidate("c1", "example.com", "Example")]
        self.assertIsNone(normalization.find_duplicate_candidate(existing, "other.com"))


class FindDuplicateCandidateByNameTests(unittest.TestCase):
    def test_matches_a_different_domain_with_the_same_normalized_name(self) -> None:
        existing = [_candidate("c1", "example.com", "Example Platform"), _candidate("c2", "example.co.uk", "example platform")]
        match = normalization.find_duplicate_candidate_by_name(existing, "example platform", exclude_candidate_id="c2")
        self.assertIsNotNone(match)
        self.assertEqual(match.candidate_id, "c1")

    def test_excludes_the_candidate_itself(self) -> None:
        existing = [_candidate("c1", "example.com", "Example Platform")]
        self.assertIsNone(normalization.find_duplicate_candidate_by_name(existing, "example platform", exclude_candidate_id="c1"))


if __name__ == "__main__":
    unittest.main()
