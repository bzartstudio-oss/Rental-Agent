"""Where every installed ranking rule is known — mirrors `FilterRegistry`/
`GeoProviderRegistry`'s self-registration + eager-import shape. See
docs/27_Intelligent_Ranking_Engine.md "Plugin System" — "Adding a new ranking rule
must require zero modifications to RankingEngineV2" is this registry's entire
reason to exist.

Rules register **instances**, not classes — no built-in rule has any per-call
construction parameter, the same reasoning `FilterRegistry`/`GeoProviderRegistry`
already applied to their own domains.
"""

from __future__ import annotations

from src.ranking_v2.base_rule import RankingRule
from src.ranking_v2.exceptions import RankingConfigurationError


class RankingRuleRegistry:
    _rules: dict[str, RankingRule] = {}

    @classmethod
    def register(cls, rule: RankingRule) -> RankingRule:
        if not isinstance(rule, RankingRule):
            raise RankingConfigurationError(
                f"{rule!r} is not a RankingRule instance — register_ranking_rule() "
                "must be called with an instantiated RankingRule subclass"
            )
        if not getattr(rule, "rule_key", None):
            raise RankingConfigurationError(
                f"{type(rule).__name__} must set a class-level `rule_key` before it can be registered"
            )
        cls._rules[rule.rule_key] = rule
        return rule

    @classmethod
    def get(cls, rule_key: str) -> RankingRule:
        try:
            return cls._rules[rule_key]
        except KeyError:
            raise RankingConfigurationError(
                f"No ranking rule registered for {rule_key!r}. Registered: {sorted(cls._rules)}"
            ) from None

    @classmethod
    def all(cls) -> list[RankingRule]:
        return list(cls._rules.values())

    @classmethod
    def is_registered(cls, rule_key: str) -> bool:
        return rule_key in cls._rules

    @classmethod
    def reset(cls) -> None:
        """Test-only: clears every registered ranking rule. Real code never calls this."""
        cls._rules.clear()


def register_ranking_rule(rule: RankingRule) -> RankingRule:
    return RankingRuleRegistry.register(rule)
