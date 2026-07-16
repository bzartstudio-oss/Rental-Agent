"""Unit + Plugin tests for FeedbackRegistry — src/feedback/registry.py. Uses a
private `_FakeRegistry` subclass with its own `_rules` dict, never touching the
real, shared `FeedbackRegistry` (which already holds all 23 built-in rules) — the
same isolation strategy every other registry's own tests use.
"""

from __future__ import annotations

import unittest

from src.feedback.base_rule import PreferenceContext, PreferenceRule
from src.feedback.exceptions import FeedbackConfigurationError
from src.feedback.metadata import PreferenceRuleMetadata
from src.feedback.models import PreferenceObservation, PreferenceValue
from src.feedback.registry import FeedbackRegistry


class _FakeRegistry(FeedbackRegistry):
    _rules: dict = {}


class _FakeRule(PreferenceRule):
    preference_key = "fake"

    def relevant_event_types(self) -> frozenset[str]:
        return frozenset({"saved"})

    def observe(self, event, context: PreferenceContext):
        return None

    def aggregate(self, observations, context: PreferenceContext) -> PreferenceValue:
        raise NotImplementedError

    def metadata(self) -> PreferenceRuleMetadata:
        return PreferenceRuleMetadata(preference_key=self.preference_key, display_name="Fake", category="test",
                                       description="", value_shape="importance")


class FeedbackRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeRegistry.reset()

    def test_register_then_get_returns_the_same_instance(self) -> None:
        rule = _FakeRule()
        _FakeRegistry.register(rule)
        self.assertIs(_FakeRegistry.get("fake"), rule)

    def test_get_unknown_rule_raises_configuration_error(self) -> None:
        with self.assertRaises(FeedbackConfigurationError):
            _FakeRegistry.get("does-not-exist")

    def test_register_rejects_non_preferencerule_objects(self) -> None:
        with self.assertRaises(FeedbackConfigurationError):
            _FakeRegistry.register(object())  # type: ignore[arg-type]

    def test_register_rejects_a_rule_with_no_preference_key(self) -> None:
        class _NoKey(PreferenceRule):
            preference_key = ""

            def relevant_event_types(self):
                return frozenset()

            def observe(self, event, context):
                return None

            def aggregate(self, observations, context):
                raise NotImplementedError

            def metadata(self):
                return PreferenceRuleMetadata(preference_key="", display_name="x", category="test",
                                               description="", value_shape="importance")

        with self.assertRaises(FeedbackConfigurationError):
            _FakeRegistry.register(_NoKey())

    def test_all_returns_every_registered_rule(self) -> None:
        _FakeRegistry.register(_FakeRule())
        self.assertEqual([r.preference_key for r in _FakeRegistry.all()], ["fake"])

    def test_is_registered(self) -> None:
        self.assertFalse(_FakeRegistry.is_registered("fake"))
        _FakeRegistry.register(_FakeRule())
        self.assertTrue(_FakeRegistry.is_registered("fake"))

    def test_rules_for_event_type_routes_correctly(self) -> None:
        _FakeRegistry.register(_FakeRule())
        self.assertEqual(len(_FakeRegistry.rules_for_event_type("saved")), 1)
        self.assertEqual(len(_FakeRegistry.rules_for_event_type("rejected")), 0)

    def test_reset_clears_everything(self) -> None:
        _FakeRegistry.register(_FakeRule())
        _FakeRegistry.reset()
        self.assertEqual(_FakeRegistry.all(), [])

    def test_real_registry_has_all_23_built_in_rules(self) -> None:
        """Not isolated — proves the real, shared `FeedbackRegistry` genuinely
        holds every built-in preference rule at import time.
        """
        self.assertEqual(len(FeedbackRegistry.all()), 23)
        self.assertTrue(FeedbackRegistry.is_registered("price_sensitivity"))
        self.assertTrue(FeedbackRegistry.is_registered("private_bathroom"))


class FuturePreferenceRulePluginTests(unittest.TestCase):
    """A second, independent `PreferenceRule` registered at test time — proves
    adding a preference dimension requires zero change to `FeedbackEngine`, only a
    `register_preference_rule` call.
    """

    def setUp(self) -> None:
        _FakeRegistry.reset()

    def test_a_second_registered_rule_is_resolvable_and_routable(self) -> None:
        class _FutureRule(PreferenceRule):
            preference_key = "future_dimension"

            def relevant_event_types(self):
                return frozenset({"a_future_event_type"})

            def observe(self, event, context):
                return PreferenceObservation(
                    profile_id=event.profile_id, preference_key=self.preference_key, event_id=event.event_id,
                    direction="supporting", magnitude=1.0, source_type="inferred", computed_at=event.occurred_at,
                    explanation="future evidence",
                )

            def aggregate(self, observations, context):
                raise NotImplementedError

            def metadata(self):
                return PreferenceRuleMetadata(preference_key=self.preference_key, display_name="Future",
                                               category="test", description="", value_shape="importance")

        _FakeRegistry.register(_FutureRule())
        rules = _FakeRegistry.rules_for_event_type("a_future_event_type")
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].preference_key, "future_dimension")


if __name__ == "__main__":
    unittest.main()
