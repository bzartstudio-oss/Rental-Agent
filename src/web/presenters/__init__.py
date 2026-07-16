"""Presentation models — see docs/32_Web_Dashboard.md "Presenters".

Pure formatting only: labeling a value as confirmed/estimated/inferred/
unavailable, converting a dataclass to a JSON-safe dict, choosing a display
string for an enum. No method here computes a score, applies a filter, or
decides eligibility — every number displayed was already computed by the
engine that owns it.
"""

from __future__ import annotations
