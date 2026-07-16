"""`FeedbackEventType` — named string constants for the mission's own required event
types. A plain class of string constants, not a `str, Enum` restricting
`FeedbackEvent.event_type`'s actual field type — the same "open-ended by
convention" reasoning `src.geography.nearby_search.NEARBY_CATEGORIES` already
established: "Future event types must be addable without changing FeedbackEngine"
(the mission's own words) means a future event type is just a new string passed to
`record_event()`, never a code change here or anywhere `FeedbackEngine` iterates
event types generically.
"""

from __future__ import annotations


class FeedbackEventType:
    VIEWED = "viewed"
    SAVED = "saved"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"
    CONTACTED = "contacted"
    IGNORED = "ignored"
    MANUAL_RATING = "manual_rating"
    MANUAL_RANKING_UP = "manual_ranking_up"
    MANUAL_RANKING_DOWN = "manual_ranking_down"
    FILTER_SELECTED = "filter_selected"
    FILTER_REMOVED = "filter_removed"
    WEIGHT_CHANGED = "weight_changed"
    SEARCH_REPEATED = "search_repeated"
    RESULT_OPENED = "result_opened"
    ORIGINAL_LISTING_OPENED = "original_listing_opened"


# Every named constant above, for validation/enumeration convenience only — a
# caller may still record any other string; this set is not enforced anywhere.
KNOWN_EVENT_TYPES: frozenset[str] = frozenset(
    value for key, value in vars(FeedbackEventType).items() if not key.startswith("_")
)

# Event types that represent explicit, direct user intent — always trusted more
# than an inferred behavioral pattern (see docs/28 "Explicit versus Inferred").
EXPLICIT_EVENT_TYPES: frozenset[str] = frozenset(
    {
        FeedbackEventType.MANUAL_RATING,
        FeedbackEventType.MANUAL_RANKING_UP,
        FeedbackEventType.MANUAL_RANKING_DOWN,
        FeedbackEventType.WEIGHT_CHANGED,
    }
)

# Event types that represent a positive signal toward whatever apartment/filter
# they're attached to.
POSITIVE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        FeedbackEventType.SAVED,
        FeedbackEventType.SHORTLISTED,
        FeedbackEventType.CONTACTED,
        FeedbackEventType.MANUAL_RANKING_UP,
        FeedbackEventType.FILTER_SELECTED,
    }
)

# Event types that represent a negative signal.
NEGATIVE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        FeedbackEventType.REJECTED,
        FeedbackEventType.IGNORED,
        FeedbackEventType.MANUAL_RANKING_DOWN,
        FeedbackEventType.FILTER_REMOVED,
    }
)
