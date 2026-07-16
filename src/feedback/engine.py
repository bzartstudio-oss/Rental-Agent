"""`FeedbackEngine` — the orchestrator implementing every auditability method the
mission requires: `record_event`, `build_preference_profile`,
`get_preference_history`, `explain_preference`, `undo_preference_adjustment`,
`reset_inferred_preferences`, `export_feedback_history`,
`compare_preference_profiles`. See
docs/28_User_Feedback_and_Preference_Learning.md "Architecture"/"Auditability".

**The adjustment log is the source of truth for "current" values, not a
recomputed-every-time aggregate.** `build_preference_profile()` computes what the
current aggregate *would* be from persisted observations (respecting any reset/undo
cutoff — see `_effective_cutoff()`) and only writes a new `PreferenceAdjustment` row
when that differs from the last one on file — the same "detect and record a real
change" discipline `FilterConfiguration`/`ProviderHealth` already apply elsewhere.
This is what makes `undo_preference_adjustment()`/`reset_inferred_preferences()`
genuinely effective rather than immediately overwritten by the next rebuild: both
write a new adjustment whose `applied_at` becomes the new evidence cutoff, so only
*future* events can out-vote a manual undo/reset — exactly "Do not automatically
change a user's saved preferences without recording why" (the mission's own words).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from src.feedback import service as feedback_service
from src.feedback.base_rule import PreferenceContext
from src.feedback.decay import DecayConfig, DEFAULT_DECAY_CONFIG
from src.feedback.exceptions import FeedbackConfigurationError, FeedbackValidationError
from src.feedback.models import (
    FeedbackEvent,
    FeedbackMode,
    FeedbackStatistics,
    PreferenceAdjustment,
    PreferenceConfidence,
    PreferenceEvidence,
    PreferenceProfile,
    PreferenceValue,
)
from src.feedback.registry import FeedbackRegistry
from src.geography.models import GeoEnrichment
from src.storage.models import Apartment

_RESET_LIKE_TYPES = frozenset({"reset", "undo"})


class FeedbackEngine:
    def __init__(self, decay_config: DecayConfig | None = None) -> None:
        self.decay_config = decay_config or DEFAULT_DECAY_CONFIG

    # ------------------------------------------------------------------ #
    # record_event
    # ------------------------------------------------------------------ #

    def record_event(
        self,
        conn: sqlite3.Connection,
        event: FeedbackEvent,
        *,
        apartment: Apartment | None = None,
        geo_enrichment: GeoEnrichment | None = None,
        location: str | None = None,
    ) -> FeedbackEvent:
        """Appends `event` (append-only — never overwritten), then immediately
        runs every relevant registered `PreferenceRule.observe()` against it,
        persisting any resulting `PreferenceObservation`. `apartment`/
        `geo_enrichment`/`location` are optional context for rules that need them
        (e.g. `price_sensitivity` needs `apartment`+`location`); a rule with no
        usable evidence from this event honestly produces nothing.
        """
        if not event.profile_id:
            raise FeedbackValidationError("FeedbackEvent.profile_id is required")
        if not event.event_type:
            raise FeedbackValidationError("FeedbackEvent.event_type is required")

        feedback_service.record_event(conn, event)

        context = PreferenceContext(
            conn=conn, apartment=apartment, geo_enrichment=geo_enrichment, location=location,
            now=event.occurred_at, decay_config=self.decay_config,
        )
        for rule in FeedbackRegistry.rules_for_event_type(event.event_type):
            observation = rule.observe(event, context)
            if observation is not None:
                feedback_service.record_observation(conn, observation)

        return event

    # ------------------------------------------------------------------ #
    # build_preference_profile
    # ------------------------------------------------------------------ #

    def build_preference_profile(
        self,
        conn: sqlite3.Connection,
        profile_id: str,
        *,
        mode: FeedbackMode = FeedbackMode.SUGGESTED,
        explicit_settings: dict | None = None,
        now: datetime | None = None,
    ) -> PreferenceProfile:
        now = now or datetime.now(timezone.utc)
        explicit_settings = explicit_settings or {}
        preferences: dict[str, PreferenceValue] = {}

        for rule in FeedbackRegistry.all():
            key = rule.preference_key

            if key in explicit_settings:
                value = self._explicit_value(key, explicit_settings[key], now)
                adjustment_type = "explicit"
            else:
                cutoff = self._effective_cutoff(conn, profile_id, key)
                observations = feedback_service.get_observations(conn, profile_id, key)
                if cutoff is not None:
                    observations = [o for o in observations if o.computed_at > cutoff]
                context = PreferenceContext(conn=conn, now=now, decay_config=self.decay_config)
                value = rule.aggregate(observations, context)
                adjustment_type = "inferred"

            self._record_adjustment_if_changed(conn, profile_id, key, value, now, adjustment_type)
            value.history = feedback_service.get_adjustments(conn, profile_id, key)
            preferences[key] = value

        profile = PreferenceProfile(
            profile_id=profile_id, mode=mode, preferences=preferences,
            explicit_settings=explicit_settings, computed_at=now,
        )
        self._persist_snapshot(conn, profile, reason="build_preference_profile", now=now)
        return profile

    def _explicit_value(self, preference_key: str, raw_value, now: datetime) -> PreferenceValue:
        current_value = raw_value if isinstance(raw_value, dict) else {"value": raw_value}
        return PreferenceValue(
            preference_key=preference_key, current_value=current_value,
            confidence=PreferenceConfidence(overall=1.0, supporting_evidence_count=0, opposing_evidence_count=0,
                                             explicit_count=1, inferred_count=0),
            source_types={"explicit"}, last_updated=now,
            explanation=f"Explicit user setting: {current_value!r}", is_explicit=True,
        )

    def _effective_cutoff(self, conn: sqlite3.Connection, profile_id: str, preference_key: str) -> datetime | None:
        adjustments = feedback_service.get_adjustments(conn, profile_id, preference_key)
        reset_like = [a for a in adjustments if a.adjustment_type in _RESET_LIKE_TYPES]
        return max((a.applied_at for a in reset_like), default=None)

    def _record_adjustment_if_changed(
        self, conn: sqlite3.Connection, profile_id: str, preference_key: str,
        value: PreferenceValue, now: datetime, adjustment_type: str,
    ) -> None:
        existing = feedback_service.get_adjustments(conn, profile_id, preference_key)
        latest = existing[-1] if existing else None

        if latest is not None and latest.new_value == value.current_value and latest.new_confidence == value.confidence.overall:
            return  # no real change — never write a no-op adjustment row

        adjustment = PreferenceAdjustment(
            profile_id=profile_id, preference_key=preference_key,
            reason=f"Recomputed from {value.confidence.supporting_evidence_count + value.confidence.opposing_evidence_count} observation(s)"
                   if adjustment_type == "inferred" else "Explicit user setting applied",
            triggered_by_event_ids=[], adjustment_type=adjustment_type, applied_at=now,
            previous_value=latest.new_value if latest else None,
            new_value=value.current_value,
            previous_confidence=latest.new_confidence if latest else None,
            new_confidence=value.confidence.overall,
        )
        feedback_service.record_adjustment(conn, adjustment)

    def _persist_snapshot(self, conn: sqlite3.Connection, profile: PreferenceProfile, reason: str, now: datetime) -> None:
        snapshot = {
            "profile_id": profile.profile_id, "mode": profile.mode.value,
            "explicit_settings": profile.explicit_settings,
            "preferences": {
                key: {"current_value": v.current_value, "confidence": v.confidence.overall, "is_explicit": v.is_explicit}
                for key, v in profile.preferences.items()
            },
        }
        feedback_service.record_snapshot(conn, profile.profile_id, snapshot, reason, now)

    # ------------------------------------------------------------------ #
    # get_preference_history / explain_preference
    # ------------------------------------------------------------------ #

    def get_preference_history(
        self, conn: sqlite3.Connection, profile_id: str, preference_key: str
    ) -> list[PreferenceAdjustment]:
        return feedback_service.get_adjustments(conn, profile_id, preference_key)

    def explain_preference(
        self, conn: sqlite3.Connection, profile_id: str, preference_key: str, *, now: datetime | None = None
    ) -> PreferenceEvidence:
        now = now or datetime.now(timezone.utc)
        cutoff = self._effective_cutoff(conn, profile_id, preference_key)
        observations = feedback_service.get_observations(conn, profile_id, preference_key)
        if cutoff is not None:
            observations = [o for o in observations if o.computed_at > cutoff]
        return PreferenceEvidence(profile_id=profile_id, preference_key=preference_key, observations=observations)

    # ------------------------------------------------------------------ #
    # undo / reset
    # ------------------------------------------------------------------ #

    def undo_preference_adjustment(
        self, conn: sqlite3.Connection, profile_id: str, preference_key: str, adjustment_id: int,
        *, now: datetime | None = None,
    ) -> PreferenceAdjustment:
        now = now or datetime.now(timezone.utc)
        target = feedback_service.get_adjustment_by_id(conn, adjustment_id)
        if target is None or target.profile_id != profile_id or target.preference_key != preference_key:
            raise FeedbackConfigurationError(
                f"No adjustment {adjustment_id!r} found for profile {profile_id!r}/preference {preference_key!r}"
            )

        undo = PreferenceAdjustment(
            profile_id=profile_id, preference_key=preference_key,
            reason=f"Undo of adjustment #{adjustment_id} ({target.reason!r})", triggered_by_event_ids=[],
            adjustment_type="undo", applied_at=now, previous_value=target.new_value, new_value=target.previous_value,
            previous_confidence=target.new_confidence, new_confidence=target.previous_confidence,
            reverses_adjustment_id=adjustment_id,
        )
        new_id = feedback_service.record_adjustment(conn, undo)
        undo.id = new_id
        return undo

    def reset_inferred_preferences(
        self, conn: sqlite3.Connection, profile_id: str, *, now: datetime | None = None
    ) -> list[PreferenceAdjustment]:
        """Reverts every *inferred* preference to a neutral, no-evidence state —
        never touches a preference whose latest adjustment is `"explicit"` (see
        this module's own docstring: "Explicit user profile settings always take
        precedence"). Never deletes a `FeedbackEvent`/`PreferenceObservation` —
        only moves the evidence cutoff forward (`_effective_cutoff()`), so raw
        history remains fully intact and inspectable.
        """
        now = now or datetime.now(timezone.utc)
        reset_adjustments: list[PreferenceAdjustment] = []

        for rule in FeedbackRegistry.all():
            key = rule.preference_key
            existing = feedback_service.get_adjustments(conn, profile_id, key)
            latest = existing[-1] if existing else None
            if latest is None or latest.adjustment_type == "explicit":
                continue

            reset = PreferenceAdjustment(
                profile_id=profile_id, preference_key=key, reason="Reset inferred preference to neutral",
                triggered_by_event_ids=[], adjustment_type="reset", applied_at=now,
                previous_value=latest.new_value, new_value=None,
                previous_confidence=latest.new_confidence, new_confidence=0.0,
            )
            new_id = feedback_service.record_adjustment(conn, reset)
            reset.id = new_id
            reset_adjustments.append(reset)

        return reset_adjustments

    # ------------------------------------------------------------------ #
    # export / compare
    # ------------------------------------------------------------------ #

    def export_feedback_history(self, conn: sqlite3.Connection, profile_id: str) -> list[FeedbackEvent]:
        return feedback_service.get_events_for_profile(conn, profile_id)

    def compare_preference_profiles(
        self, conn: sqlite3.Connection, profile_id_a: str, profile_id_b: str, *, now: datetime | None = None
    ) -> dict:
        now = now or datetime.now(timezone.utc)
        profile_a = self.build_preference_profile(conn, profile_id_a, now=now)
        profile_b = self.build_preference_profile(conn, profile_id_b, now=now)

        differences = {}
        for key in FeedbackRegistry.all():
            pref_key = key.preference_key
            value_a = profile_a.preferences.get(pref_key)
            value_b = profile_b.preferences.get(pref_key)
            if value_a.current_value != value_b.current_value:
                differences[pref_key] = {
                    profile_id_a: value_a.current_value,
                    profile_id_b: value_b.current_value,
                }

        return {
            "profile_a": profile_id_a, "profile_b": profile_id_b, "compared_at": now.isoformat(),
            "differences": differences,
        }

    # ------------------------------------------------------------------ #
    # statistics
    # ------------------------------------------------------------------ #

    def compute_statistics(self, conn: sqlite3.Connection, profile_id: str) -> FeedbackStatistics:
        events = feedback_service.get_events_for_profile(conn, profile_id)
        events_by_type: dict[str, int] = {}
        for event in events:
            events_by_type[event.event_type] = events_by_type.get(event.event_type, 0) + 1

        from src.feedback.event_types import EXPLICIT_EVENT_TYPES

        explicit_count = sum(1 for e in events if e.event_type in EXPLICIT_EVENT_TYPES)

        return FeedbackStatistics(
            profile_id=profile_id, total_events=len(events), events_by_type=events_by_type,
            explicit_event_count=explicit_count, inferred_event_count=len(events) - explicit_count,
            first_event_at=events[0].occurred_at if events else None,
            last_event_at=events[-1].occurred_at if events else None,
        )
