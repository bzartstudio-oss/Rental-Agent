"""`PreferenceRuleMetadata` — a preference rule's static self-description, mirroring
`FilterMetadata`/`GeoProviderMetadata`/`RankingRuleMetadata`'s same declarative-
capability-discovery role. See docs/28_User_Feedback_and_Preference_Learning.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PreferenceRuleMetadata:
    preference_key: str
    display_name: str
    category: str
    description: str
    value_shape: str  # "importance" | "threshold" | "categorical" | "boolean"
    learns_from_listing_fields: bool = True  # False for Group-B "dormant field" preferences
    relevant_event_types: frozenset[str] = field(default_factory=frozenset)
