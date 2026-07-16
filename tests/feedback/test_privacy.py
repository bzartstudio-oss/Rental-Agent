"""Privacy guardrail tests — "Do not infer sensitive personal characteristics. Do
not infer gender, ethnicity, religion, health status, sexual orientation,
political views, or other sensitive traits from browsing or rental choices" (the
mission's own words). These tests assert the *entire* set of 23 registered
preference dimensions, checked structurally rather than by example, since a new
rule added later without updating this list would otherwise slip through silently.
"""

from __future__ import annotations

import unittest

from src.feedback.registry import FeedbackRegistry

_SENSITIVE_TERMS = (
    "gender", "ethnic", "race", "racial", "religion", "religious", "health", "disability",
    "sexual", "orientation", "political", "immigration", "citizenship", "nationality",
    "pregnan", "disease", "medical",
)


class PrivacyGuardrailTests(unittest.TestCase):
    def test_no_registered_preference_key_references_a_sensitive_trait(self) -> None:
        for rule in FeedbackRegistry.all():
            key_lower = rule.preference_key.lower()
            for term in _SENSITIVE_TERMS:
                self.assertNotIn(
                    term, key_lower,
                    f"preference_key {rule.preference_key!r} appears to reference a sensitive trait ({term!r})",
                )

    def test_no_rule_metadata_description_references_a_sensitive_trait(self) -> None:
        for rule in FeedbackRegistry.all():
            description_lower = rule.metadata().description.lower()
            for term in _SENSITIVE_TERMS:
                self.assertNotIn(
                    term, description_lower,
                    f"{rule.preference_key!r}'s description appears to reference a sensitive trait ({term!r})",
                )

    def test_every_rule_operates_only_on_real_estate_relevant_fields(self) -> None:
        """Every rule's own category is a real-estate concept (cost, location,
        listing, amenity, logistics, trust) — never a category implying personal
        identity.
        """
        allowed_categories = {"cost", "location", "listing", "amenity", "logistics", "trust", "preferences", "test"}
        for rule in FeedbackRegistry.all():
            self.assertIn(rule.metadata().category, allowed_categories)

    def test_the_23_known_preference_dimensions_are_exactly_the_missions_own_list(self) -> None:
        """A structural cross-check: the full registered key set must match
        precisely what docs/28 documents — no undocumented dimension, sensitive
        or otherwise, can be silently added without this test catching it.
        """
        expected = {
            "price_sensitivity", "maximum_budget", "walking_distance", "public_transport",
            "availability_importance", "property_type", "room_type", "private_bathroom",
            "private_kitchen", "air_conditioning", "furnished", "pets_allowed", "balcony",
            "parking", "utilities_included", "internet_included", "minimum_area",
            "number_of_rooms", "number_of_flatmates", "platform", "neighborhood",
            "lifestyle", "nearby_services",
        }
        self.assertEqual({r.preference_key for r in FeedbackRegistry.all()}, expected)


if __name__ == "__main__":
    unittest.main()
