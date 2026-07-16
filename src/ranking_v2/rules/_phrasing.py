"""Shared qualitative-phrasing helper — every rule's `detail` sentence is built from
a real number, but phrased the way the mission's own example reads ("Excellent
walking distance," not "walking_distance_score=0.91"). One small shared vocabulary
keeps that tone consistent across all 12 rules instead of each rule inventing its
own adjectives.
"""

from __future__ import annotations

_BUCKETS = (
    (0.85, "Excellent"),
    (0.65, "Good"),
    (0.45, "Average"),
    (0.25, "Below-average"),
    (0.0, "Poor"),
)


def qualitative(score: float) -> str:
    for threshold, label in _BUCKETS:
        if score >= threshold:
            return label
    return "Poor"
