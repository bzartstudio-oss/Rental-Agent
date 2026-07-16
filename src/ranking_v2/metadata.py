"""`RankingRuleMetadata` — a ranking rule's static self-description, mirroring
`FilterMetadata`/`GeoProviderMetadata`'s same declarative-capability-discovery role.
See docs/27_Intelligent_Ranking_Engine.md.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RankingRuleMetadata:
    rule_key: str
    display_name: str
    category: str
    description: str
    requires_context: bool = False  # True when this rule is dormant without optional context
