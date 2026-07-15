"""The `Change` object every comparison in comparison.py produces — the structured,
uniform representation of "one detected difference" across every trackable field
(price, availability, title, description, coordinates, images, listing presence).

This is deliberately a different shape from storage.models.ApartmentChangeLogEntry:
that dataclass mirrors exactly one SQL table (`apartment_change_log`, used only for
title/description/coordinates-style generic fields); `Change` is the business-level
object used uniformly for *every* comparison, including price/availability/images,
which have their own dedicated history tables and are never written to
`apartment_change_log` (see docs/03_Data_Model.md). `history_service.change_timeline()`
is what reconstructs a `Change` list from all of those tables for reading.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class ChangeType:
    """String constants, not an Enum — consistent with the rest of this project's
    lightweight style (see e.g. `discovery_method` on Platform, plain strings throughout).
    """

    PRICE_CHANGED = "price_changed"
    AVAILABILITY_CHANGED = "availability_changed"
    TITLE_CHANGED = "title_changed"
    DESCRIPTION_CHANGED = "description_changed"
    COORDINATES_CHANGED = "coordinates_changed"
    IMAGE_ADDED = "image_added"
    IMAGE_REMOVED = "image_removed"
    LISTING_REMOVED = "listing_removed"
    LISTING_RETURNED = "listing_returned"
    LISTING_UPDATED = "listing_updated"


@dataclass
class Change:
    """One structured, detected difference for one apartment.

    `field_name` is the plain field this change is about ("price", "status", "title",
    "description", "coordinates", "image", "presence", "listing"); `change_type` is the
    more specific classification from `ChangeType`, needed because e.g. "presence" splits
    into `listing_removed`/`listing_returned` and "image" splits into
    `image_added`/`image_removed`. `search_id`/`platform_id`/`connector_name` are the
    "which search / which platform / which connector produced this observation" context
    the v2.0 Step 2 mission asked to track — attached to every Change rather than
    requiring a caller to join back to `search_requests`/`platforms` to find out.

    `first_seen_at`/`last_seen_at` are deliberately NOT fields here: they're apartment
    attributes that get refreshed on every observation, not something that is itself
    "compared" — see docs/03_Data_Model.md.
    """

    apartment_id: str
    change_type: str
    field_name: str
    old_value: str | None
    new_value: str | None
    observed_at: datetime
    search_id: str | None = None
    platform_id: str | None = None
    connector_name: str | None = None
