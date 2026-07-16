"""Where every installed preference rule is known — mirrors `FilterRegistry`/
`GeoProviderRegistry`/`RankingRuleRegistry`'s self-registration + eager-import
shape. See docs/28_User_Feedback_and_Preference_Learning.md "Plugin System" —
adding a new preference dimension (or a new event type an existing rule should
react to) never requires modifying `FeedbackEngine`, only a new `PreferenceRule`
and one `register_preference_rule(...)` call.
"""

from __future__ import annotations

from src.feedback.base_rule import PreferenceRule
from src.feedback.exceptions import FeedbackConfigurationError


class FeedbackRegistry:
    _rules: dict[str, PreferenceRule] = {}

    @classmethod
    def register(cls, rule: PreferenceRule) -> PreferenceRule:
        if not isinstance(rule, PreferenceRule):
            raise FeedbackConfigurationError(
                f"{rule!r} is not a PreferenceRule instance — register_preference_rule() "
                "must be called with an instantiated PreferenceRule subclass"
            )
        if not getattr(rule, "preference_key", None):
            raise FeedbackConfigurationError(
                f"{type(rule).__name__} must set a class-level `preference_key` before it can be registered"
            )
        cls._rules[rule.preference_key] = rule
        return rule

    @classmethod
    def get(cls, preference_key: str) -> PreferenceRule:
        try:
            return cls._rules[preference_key]
        except KeyError:
            raise FeedbackConfigurationError(
                f"No preference rule registered for {preference_key!r}. Registered: {sorted(cls._rules)}"
            ) from None

    @classmethod
    def all(cls) -> list[PreferenceRule]:
        return list(cls._rules.values())

    @classmethod
    def is_registered(cls, preference_key: str) -> bool:
        return preference_key in cls._rules

    @classmethod
    def rules_for_event_type(cls, event_type: str) -> list[PreferenceRule]:
        """Every registered rule that declares interest in `event_type` — the
        routing mechanism `FeedbackEngine.record_event()` uses so it never needs
        its own hardcoded event-type-to-rule mapping.
        """
        return [rule for rule in cls._rules.values() if event_type in rule.relevant_event_types()]

    @classmethod
    def reset(cls) -> None:
        """Test-only: clears every registered preference rule. Real code never calls this."""
        cls._rules.clear()


def register_preference_rule(rule: PreferenceRule) -> PreferenceRule:
    return FeedbackRegistry.register(rule)
