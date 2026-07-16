"""The User Feedback and Preference Learning Engine — a modular, deterministic,
explainable system that learns user preferences from explicit, traceable
evidence. See docs/28_User_Feedback_and_Preference_Learning.md.

Importing this package imports `feedback.rules`, which is what runs every
built-in preference rule's `register_preference_rule(...)` call. Public API
re-exported here so callers don't need to know this package's internal file
layout — mirrors `src.ranking_v2`/`src.geography`'s own re-export shape.
"""

from __future__ import annotations

from src.feedback import rules as _rules  # noqa: F401 — import for self-registration side effect
from src.feedback.base_rule import (
    BooleanPreferenceRule,
    CategoricalPreferenceRule,
    ImportancePreferenceRule,
    PreferenceContext,
    PreferenceRule,
    ThresholdPreferenceRule,
)
from src.feedback.decay import DecayConfig, DEFAULT_DECAY_CONFIG
from src.feedback.engine import FeedbackEngine
from src.feedback.event_types import (
    EXPLICIT_EVENT_TYPES,
    KNOWN_EVENT_TYPES,
    NEGATIVE_EVENT_TYPES,
    POSITIVE_EVENT_TYPES,
    FeedbackEventType,
)
from src.feedback.exceptions import FeedbackConfigurationError, FeedbackException, FeedbackValidationError
from src.feedback.metadata import PreferenceRuleMetadata
from src.feedback.models import (
    FeedbackEvent,
    FeedbackMode,
    FeedbackStatistics,
    PreferenceAdjustment,
    PreferenceConfidence,
    PreferenceEvidence,
    PreferenceObservation,
    PreferenceProfile,
    PreferenceSummary,
    PreferenceValue,
)
from src.feedback.filter_integration import record_filter_change_events, record_filter_selection_events
from src.feedback.ranking_adapter import resolve_ranking_profile, suggest_ranking_profile, suggest_ranking_weights
from src.feedback.registry import FeedbackRegistry, register_preference_rule

__all__ = [
    "BooleanPreferenceRule",
    "CategoricalPreferenceRule",
    "ImportancePreferenceRule",
    "PreferenceContext",
    "PreferenceRule",
    "ThresholdPreferenceRule",
    "DecayConfig",
    "DEFAULT_DECAY_CONFIG",
    "FeedbackEngine",
    "EXPLICIT_EVENT_TYPES",
    "KNOWN_EVENT_TYPES",
    "NEGATIVE_EVENT_TYPES",
    "POSITIVE_EVENT_TYPES",
    "FeedbackEventType",
    "FeedbackException",
    "FeedbackConfigurationError",
    "FeedbackValidationError",
    "PreferenceRuleMetadata",
    "FeedbackEvent",
    "FeedbackMode",
    "FeedbackStatistics",
    "PreferenceAdjustment",
    "PreferenceConfidence",
    "PreferenceEvidence",
    "PreferenceObservation",
    "PreferenceProfile",
    "PreferenceSummary",
    "PreferenceValue",
    "FeedbackRegistry",
    "register_preference_rule",
    "record_filter_change_events",
    "record_filter_selection_events",
    "resolve_ranking_profile",
    "suggest_ranking_profile",
    "suggest_ranking_weights",
]
