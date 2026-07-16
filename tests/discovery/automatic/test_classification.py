"""Tests for `discovery.automatic.classification` — deterministic, explainable
keyword-scoring classification.
"""

from __future__ import annotations

import unittest

from src.discovery.automatic.classification import classify_candidate, explain_classification
from src.discovery.automatic.models import PlatformClassification


class ClassifyCandidateTests(unittest.TestCase):
    def test_rental_marketplace_keywords_win(self) -> None:
        classification, scores = classify_candidate("Find your next rental — apartments for rent")
        self.assertEqual(classification, PlatformClassification.RENTAL_MARKETPLACE)
        self.assertGreater(scores[PlatformClassification.RENTAL_MARKETPLACE.value], 0)

    def test_shared_housing_keywords_win(self) -> None:
        classification, _ = classify_candidate("Looking for a flatshare or roommate? Room to rent here.")
        self.assertEqual(classification, PlatformClassification.SHARED_HOUSING_PLATFORM)

    def test_student_housing_keywords_win(self) -> None:
        classification, _ = classify_candidate("University housing and student accommodation portal")
        self.assertEqual(classification, PlatformClassification.STUDENT_HOUSING_PLATFORM)

    def test_no_keyword_match_returns_unknown_never_a_guess(self) -> None:
        classification, scores = classify_candidate("Completely unrelated text about cooking recipes")
        self.assertEqual(classification, PlatformClassification.UNKNOWN)
        self.assertTrue(all(score == 0 for score in scores.values()))

    def test_is_case_insensitive(self) -> None:
        # "short-term stay"/"nightly rate" (unlike "vacation rental"/"holiday rental")
        # share no substring with any RENTAL_MARKETPLACE keyword, so this isolates
        # the case-insensitivity check to VACATION_RENTAL_PLATFORM alone.
        classification, _ = classify_candidate("SHORT-TERM STAY specialists with NIGHTLY RATE bookings")
        self.assertEqual(classification, PlatformClassification.VACATION_RENTAL_PLATFORM)

    def test_deterministic_across_repeated_calls(self) -> None:
        text = "estate agency and letting agent services, also some rent listings"
        first = classify_candidate(text)
        second = classify_candidate(text)
        self.assertEqual(first, second)


class ExplainClassificationTests(unittest.TestCase):
    def test_explanation_names_matching_keyword_count(self) -> None:
        classification, scores = classify_candidate("apartments for rent, rental listings")
        explanation = explain_classification(classification, scores)
        self.assertIn(classification.value, explanation)
        self.assertIn(str(scores[classification.value]), explanation)

    def test_unknown_explanation_is_honest_about_no_match(self) -> None:
        explanation = explain_classification(PlatformClassification.UNKNOWN, {})
        self.assertIn("No category keywords matched", explanation)


if __name__ == "__main__":
    unittest.main()
