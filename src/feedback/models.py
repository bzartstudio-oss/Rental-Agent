"""Shared shapes for the User Feedback and Preference Learning Engine. See
docs/28_User_Feedback_and_Preference_Learning.md "Architecture".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class FeedbackMode(str, Enum):
    """"Support three modes" (the mission's own words) — how a suggested
    `PreferenceProfile` may influence `RankingEngineV2`. See
    `src.feedback.ranking_adapter` and docs/28 "Ranking Integration".
    """

    EXPLICIT_ONLY = "explicit_only"  # ignore inferred preferences entirely
    SUGGESTED = "suggested"  # compute suggested weights, never apply them automatically
    ASSISTED = "assisted"  # apply learned adjustments, recording every one


@dataclass
class FeedbackEvent:
    """One recorded user action — the append-only atomic unit of evidence this
    entire package is built on. `event_id` is generated here (a real UUID), not
    left to the caller, so every event is uniquely identifiable the moment it's
    constructed, before it's ever persisted.
    """

    profile_id: str
    event_type: str
    occurred_at: datetime
    source: str
    event_value: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    search_id: str | None = None
    apartment_id: str | None = None
    session_id: str | None = None
    ranking_profile: dict | None = None
    search_filters: dict | None = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class PreferenceObservation:
    """One `PreferenceRule`'s verdict on one `FeedbackEvent` — "direction" is
    "supporting" or "opposing" the rule's current inferred value; "magnitude" is
    how strongly, in `[0, 1]`, before any confidence/decay weighting is applied.
    Never fabricated: a rule that finds nothing relevant in an event simply
    produces no observation at all (see `PreferenceRule.observe()`'s own contract).
    """

    profile_id: str
    preference_key: str
    event_id: str
    direction: str  # "supporting" | "opposing"
    magnitude: float
    source_type: str  # "explicit" | "inferred"
    computed_at: datetime
    explanation: str
    observed_value: dict | None = None


@dataclass
class PreferenceEvidence:
    """The full, aggregated evidence behind one preference — every observation
    that ever contributed, split by direction and source type. This is what
    `explain_preference()` returns: enough detail to answer "what was learned, why,
    and from which events" without re-querying the database.
    """

    profile_id: str
    preference_key: str
    observations: list[PreferenceObservation] = field(default_factory=list)

    @property
    def supporting_count(self) -> int:
        return sum(1 for o in self.observations if o.direction == "supporting")

    @property
    def opposing_count(self) -> int:
        return sum(1 for o in self.observations if o.direction == "opposing")

    @property
    def explicit_count(self) -> int:
        return sum(1 for o in self.observations if o.source_type == "explicit")

    @property
    def inferred_count(self) -> int:
        return sum(1 for o in self.observations if o.source_type == "inferred")

    @property
    def source_types(self) -> set[str]:
        return {o.source_type for o in self.observations}

    @property
    def triggering_event_ids(self) -> list[str]:
        return [o.event_id for o in self.observations]


@dataclass
class PreferenceAdjustment:
    """One row of the append-only adjustment log — every time a preference's
    computed value/confidence actually changed. `id` is `None` until persisted.
    `reverses_adjustment_id` is set only on an "undo" row — the mechanism by which
    an adjustment is reversed without ever deleting or rewriting the original.
    """

    profile_id: str
    preference_key: str
    reason: str
    triggered_by_event_ids: list[str]
    adjustment_type: str  # "inferred" | "explicit" | "undo" | "reset"
    applied_at: datetime
    previous_value: dict | None = None
    new_value: dict | None = None
    previous_confidence: float | None = None
    new_confidence: float | None = None
    reverses_adjustment_id: int | None = None
    id: int | None = None


@dataclass
class PreferenceConfidence:
    """How much to trust one preference's current value — mirrors
    `RankingConfidence`'s own honesty-first reasoning: a preference inferred from
    one ambiguous event should never read as confidently as one confirmed by many
    consistent explicit actions.
    """

    overall: float
    supporting_evidence_count: int
    opposing_evidence_count: int
    explicit_count: int
    inferred_count: int


@dataclass
class PreferenceValue:
    """Every preference must include: current value, confidence, supporting
    evidence count, opposing evidence count, source types, last updated,
    explanation, history" (the mission's own words) — every one of those is a
    field here.
    """

    preference_key: str
    current_value: dict | None
    confidence: PreferenceConfidence
    source_types: set[str]
    last_updated: datetime | None
    explanation: str
    history: list[PreferenceAdjustment] = field(default_factory=list)
    is_explicit: bool = False


@dataclass
class PreferenceProfile:
    """The complete, current preference picture for one profile_id — one
    `PreferenceValue` per known preference key. `explicit_settings` are raw,
    directly-set user values (always authoritative — see
    docs/28 "Explicit versus Inferred") kept alongside the computed
    `preferences` map so a caller never has to guess which one wins.
    """

    profile_id: str
    mode: FeedbackMode
    preferences: dict[str, PreferenceValue] = field(default_factory=dict)
    explicit_settings: dict = field(default_factory=dict)
    computed_at: datetime | None = None

    def get(self, preference_key: str) -> PreferenceValue | None:
        return self.preferences.get(preference_key)


@dataclass
class PreferenceSummary:
    """A compact, report/CLI-friendly overview of a profile — top preferences by
    confidence, plain counts, nothing requiring a caller to walk the full
    `PreferenceProfile` tree.
    """

    profile_id: str
    generated_at: datetime
    total_preferences_tracked: int
    explicit_preference_count: int
    inferred_preference_count: int
    top_preferences: list[tuple[str, PreferenceValue]] = field(default_factory=list)


@dataclass
class FeedbackStatistics:
    """Aggregate figures across a profile's whole feedback event history —
    mirrors `FilterStatistics`/`GeoStatistics`/`RankingStatistics`'s own
    "computed from completed results, never inside the engine itself" separation.
    """

    profile_id: str
    total_events: int
    events_by_type: dict[str, int] = field(default_factory=dict)
    explicit_event_count: int = 0
    inferred_event_count: int = 0
    first_event_at: datetime | None = None
    last_event_at: datetime | None = None

    def as_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "total_events": self.total_events,
            "events_by_type": self.events_by_type,
            "explicit_event_count": self.explicit_event_count,
            "inferred_event_count": self.inferred_event_count,
            "first_event_at": self.first_event_at.isoformat() if self.first_event_at else None,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
        }
