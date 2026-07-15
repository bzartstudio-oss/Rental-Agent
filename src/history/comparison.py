"""Pure comparison functions — no database access, no I/O. Each takes the old and new
value of one field and returns a structured `Change` (or `None`/`[]` when nothing
actually differs), per the v2.0 Step 2 mission: "every comparison must produce a
structured Change object." Being pure and DB-free is what makes every one of these
independently unit-testable (see tests/history/test_comparison.py) without a database.

Callers (src/history/history_service.py, src/analyzers/engine.py) decide *when* to call
these and what to do with the result (write to apartment_change_log, download an image,
etc.) — that decision-and-write responsibility deliberately stays out of this module,
matching docs/01_System_Architecture.md's "storage/ must not contain business rules"
boundary extended to comparison logic too.
"""

from __future__ import annotations

import json
from datetime import datetime

from src.history.models import Change, ChangeType


def compare_price(
    apartment_id: str,
    old_price: float | None,
    new_price: float,
    observed_at: datetime,
    *,
    search_id: str | None = None,
    platform_id: str | None = None,
    connector_name: str | None = None,
) -> Change | None:
    """Not used to decide whether to write `apartment_price_history` (that's
    `analyzers/change_detector.py::price_changed`, unchanged since v1.0) — this exists so
    `history_service.change_timeline()` can represent a price entry as a `Change` like
    every other field, for a uniform read-side timeline.
    """
    if old_price == new_price:
        return None
    return Change(
        apartment_id=apartment_id,
        change_type=ChangeType.PRICE_CHANGED,
        field_name="price",
        old_value=None if old_price is None else str(old_price),
        new_value=str(new_price),
        observed_at=observed_at,
        search_id=search_id,
        platform_id=platform_id,
        connector_name=connector_name,
    )


def compare_availability(
    apartment_id: str,
    old_status: str | None,
    new_status: str,
    observed_at: datetime,
    *,
    search_id: str | None = None,
    platform_id: str | None = None,
    connector_name: str | None = None,
) -> Change | None:
    if old_status == new_status:
        return None
    return Change(
        apartment_id=apartment_id,
        change_type=ChangeType.AVAILABILITY_CHANGED,
        field_name="status",
        old_value=old_status,
        new_value=new_status,
        observed_at=observed_at,
        search_id=search_id,
        platform_id=platform_id,
        connector_name=connector_name,
    )


def compare_title(
    apartment_id: str,
    old_title: str | None,
    new_title: str,
    observed_at: datetime,
    *,
    search_id: str | None = None,
    platform_id: str | None = None,
    connector_name: str | None = None,
) -> Change | None:
    """`old_title=None` is the first-ever observation of this apartment — matches
    `apartment_change_log`'s convention of a null `old_value` for the initial row
    (docs/03_Data_Model.md).
    """
    if old_title == new_title:
        return None
    return Change(
        apartment_id=apartment_id,
        change_type=ChangeType.TITLE_CHANGED,
        field_name="title",
        old_value=old_title,
        new_value=new_title,
        observed_at=observed_at,
        search_id=search_id,
        platform_id=platform_id,
        connector_name=connector_name,
    )


def compare_description(
    apartment_id: str,
    old_description: str | None,
    new_description: str | None,
    observed_at: datetime,
    *,
    search_id: str | None = None,
    platform_id: str | None = None,
    connector_name: str | None = None,
) -> Change | None:
    """`new_description=None` (platform provides no description) correctly produces no
    change as long as it was also `None` before — exact string inequality, per
    docs/07_Analysis_Engine.md's "Open Questions" resolution for v2.0 (a single typo fix
    reads as a real change; revisit only if that proves too noisy in practice).
    """
    if old_description == new_description:
        return None
    return Change(
        apartment_id=apartment_id,
        change_type=ChangeType.DESCRIPTION_CHANGED,
        field_name="description",
        old_value=old_description,
        new_value=new_description,
        observed_at=observed_at,
        search_id=search_id,
        platform_id=platform_id,
        connector_name=connector_name,
    )


def compare_coordinates(
    apartment_id: str,
    old_latitude: float | None,
    old_longitude: float | None,
    new_latitude: float | None,
    new_longitude: float | None,
    observed_at: datetime,
    *,
    search_id: str | None = None,
    platform_id: str | None = None,
    connector_name: str | None = None,
) -> Change | None:
    """Not yet wired into `analyzers/engine.py`'s write sequence: no connector or
    `normalizer.py` populates `latitude`/`longitude` today (docs/07_Analysis_Engine.md's
    Write Sequence UPDATE list doesn't include coordinates), and the Deep Analysis
    Engine that would supply real geocoded values is Step 7, blocked on an unmade
    vendor decision. Implemented and tested standalone now so it's ready the moment a
    connector supplies coordinates, per the v2.0 Step 2 mission's explicit "Track
    changes for: ... Coordinates" requirement.
    """
    if old_latitude == new_latitude and old_longitude == new_longitude:
        return None
    return Change(
        apartment_id=apartment_id,
        change_type=ChangeType.COORDINATES_CHANGED,
        field_name="coordinates",
        old_value=_format_coordinates(old_latitude, old_longitude),
        new_value=_format_coordinates(new_latitude, new_longitude),
        observed_at=observed_at,
        search_id=search_id,
        platform_id=platform_id,
        connector_name=connector_name,
    )


def compare_images(
    apartment_id: str,
    old_urls: list[str],
    new_urls: list[str],
    observed_at: datetime,
    *,
    search_id: str | None = None,
    platform_id: str | None = None,
    connector_name: str | None = None,
) -> list[Change]:
    """The "Image Change Detection" comparison (docs/07_Analysis_Engine.md): diffs the
    currently-known image set against this observation's. Takes lists, not sets, and
    walks them in the given order rather than sorting, so callers get a deterministic,
    input-order result — `analyzers/engine.py` relies on this to keep a brand-new
    apartment's images in their original listing order (`old_urls=[]` there, so every
    image comes back as "added" in exactly the order the connector returned them).
    """
    old_set, new_set = set(old_urls), set(new_urls)
    changes = []

    for url in new_urls:
        if url not in old_set:
            changes.append(
                Change(
                    apartment_id=apartment_id,
                    change_type=ChangeType.IMAGE_ADDED,
                    field_name="image",
                    old_value=None,
                    new_value=url,
                    observed_at=observed_at,
                    search_id=search_id,
                    platform_id=platform_id,
                    connector_name=connector_name,
                )
            )

    for url in old_urls:
        if url not in new_set:
            changes.append(
                Change(
                    apartment_id=apartment_id,
                    change_type=ChangeType.IMAGE_REMOVED,
                    field_name="image",
                    old_value=url,
                    new_value=None,
                    observed_at=observed_at,
                    search_id=search_id,
                    platform_id=platform_id,
                    connector_name=connector_name,
                )
            )

    return changes


def compare_presence(
    apartment_id: str,
    was_observed_before: bool,
    is_observed_now: bool,
    observed_at: datetime,
    *,
    search_id: str | None = None,
    platform_id: str | None = None,
    connector_name: str | None = None,
) -> Change | None:
    """"Listing Removed" / "Listing Returned". Deliberately takes explicit before/after
    presence booleans rather than inferring them from `apartments.current_status` or any
    heuristic — deciding whether an apartment was genuinely absent from a platform this
    run (as opposed to merely excluded by this run's filters) requires comparing the
    full observed set across runs, which is exactly what Search Memory
    (`search_observed_apartments`, v2.0 Step 3, docs/17_Search_Memory.md) is for and is
    NOT built yet. This function only formats the `Change` once that decision has been
    made by whichever caller has the real answer — not wired into
    `analyzers/engine.py` in this step.
    """
    if was_observed_before and not is_observed_now:
        return Change(
            apartment_id=apartment_id,
            change_type=ChangeType.LISTING_REMOVED,
            field_name="presence",
            old_value="present",
            new_value="removed",
            observed_at=observed_at,
            search_id=search_id,
            platform_id=platform_id,
            connector_name=connector_name,
        )
    if not was_observed_before and is_observed_now:
        return Change(
            apartment_id=apartment_id,
            change_type=ChangeType.LISTING_RETURNED,
            field_name="presence",
            old_value="removed",
            new_value="present",
            observed_at=observed_at,
            search_id=search_id,
            platform_id=platform_id,
            connector_name=connector_name,
        )
    return None


def summarize_listing_updated(
    apartment_id: str,
    changes: list[Change],
    observed_at: datetime,
    *,
    search_id: str | None = None,
    platform_id: str | None = None,
    connector_name: str | None = None,
) -> Change | None:
    """"Listing Updated" — a rollup `Change` for callers that just want "did anything
    change" without inspecting every itemized `Change`. Purely a convenience: unlike the
    itemized changes it summarizes, this is never written to `apartment_change_log`
    (`field_name="listing"` isn't a real column) — it's returned for the caller's own use
    (e.g. a future Knowledge Engine observation), not persisted.
    """
    if not changes:
        return None
    changed_fields = sorted({change.field_name for change in changes})
    return Change(
        apartment_id=apartment_id,
        change_type=ChangeType.LISTING_UPDATED,
        field_name="listing",
        old_value=None,
        new_value=json.dumps(changed_fields),
        observed_at=observed_at,
        search_id=search_id,
        platform_id=platform_id,
        connector_name=connector_name,
    )


def _format_coordinates(latitude: float | None, longitude: float | None) -> str | None:
    if latitude is None and longitude is None:
        return None
    return f"{latitude},{longitude}"
