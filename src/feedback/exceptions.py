"""Structured exceptions for the User Feedback and Preference Learning Engine —
mirrors `src.filter_engine.exceptions`/`src.geography.exceptions`/
`src.ranking_v2.exceptions`'s "one base class, catch one type" shape. See
docs/28_User_Feedback_and_Preference_Learning.md.
"""

from __future__ import annotations


class FeedbackException(Exception):
    """Base class for every exception this package raises."""


class FeedbackConfigurationError(FeedbackException):
    """A preference rule is misconfigured or can't be resolved — an unknown
    `preference_key`, or `register_preference_rule` given something that isn't a
    `PreferenceRule`.
    """


class FeedbackValidationError(FeedbackException):
    """A feedback event failed validation before it could be recorded — e.g. an
    empty `profile_id`, or an `event_type` string that fails basic shape checks.
    Raised by `record_event()` before anything is written — `feedback_events`
    stays append-only and never receives a malformed row.
    """
