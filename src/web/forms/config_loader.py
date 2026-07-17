"""v2.6 Milestone 2.6.3 — Configuration Loading. See
docs/41_Version_2.6_Planning.md and docs/37_Pilot_Operations_Guide.md section 9
(the manual-transcription process this loader replaces).

Before this, `config/pilot.example.json` was "a reference pilot operators read
and retype into the New Search form by hand" (its own `_meta.how_to_use`) —
nothing in the platform could load it. This module reads a JSON file matching
that same documented shape and turns it into exactly the flat, string-keyed
field set `search_form.parse_search_form()` already accepts from a real HTML
form submission, then hands it to that same, unmodified function — every
existing validation rule (required location, numeric ranges, filter
`validate()` methods) runs exactly as it does for a manually-filled form. This
is an *additional* way to reach `parse_search_form()`, not a replacement: no
existing form field, CLI flag, or filter is added, removed, or changed here.

Deliberately not translated (left for a future milestone, not silently
guessed): `destination` (no travel-time filter consumes it yet — see
docs/41 Milestone classification "Later"), `availability_date_from`/`_to` and
`minimum_stay_months`/`maximum_stay_months` (the registered filters are
`availability_date`/`minimum_stay`/`maximum_stay` — singular, differently-
shaped fields; mapping the config's range onto them would misrepresent the
config, not honor it), `ranking.ranking_profile` (the web form only supports
"default" or a `custom` per-rule weight set, not a named-profile selector),
`notifications`/`report_settings` (not part of `SearchRequest` at all), and
`save_search` (the config schema has no field for the saved search's name).

Also deliberately not translated: `property_and_room.room_type` and
`.number_of_rooms`. `room_type` (e.g. "private_room") describes what the
*pilot user* is renting, but the only registered `room_type` filter
(`preferences_and_other.py`) is dormant — `Apartment` has no such field, so
it would be a silent no-op either way. `number_of_rooms` looks like the same
concept but isn't: the registered `number_of_rooms` filter is an *exact
total-bedroom-count match* on the whole apartment (`core_filters.py`), a
different question from "how many rooms does the pilot user need in a shared
flat." Auto-mapping the config's `1` onto that filter was tried during this
milestone's own verification and produced zero results against every demo
fixture apartment (bedrooms 2/0/3) — a real defect in the translation, not in
the filter or the fixtures. Fixing it by picking a fixture-matching number
would still misrepresent what the filter actually checks, so this field is
left unmapped instead, same as `room_type`.
"""

from __future__ import annotations

import json

from werkzeug.datastructures import MultiDict

from src.web.error_handler import WebValidationError
from src.web.forms.search_form import parse_search_form

_AMENITY_KEYS = (
    "internet_included", "furnished", "private_bathroom", "air_conditioning",
    "heating", "elevator", "pets_allowed",
)


def _translate_to_form_fields(config: dict) -> MultiDict:
    search = config.get("search")
    if not isinstance(search, dict):
        raise WebValidationError("Config file must contain a top-level 'search' object")

    location = search.get("location") or {}
    fields: dict[str, str] = {
        "country": str(location.get("country") or ""),
        "region": str(location.get("region") or ""),
        "city": str(location.get("city") or ""),
        "postal_area": str(location.get("postal_area") or ""),
    }

    budget = search.get("budget") or {}
    if budget.get("min_price") is not None:
        fields["filter__min_price"] = str(budget["min_price"])
    if budget.get("max_price") is not None:
        fields["filter__max_price"] = str(budget["max_price"])
    if budget.get("currency") is not None:
        fields["filter__currency"] = str(budget["currency"])

    property_and_room = search.get("property_and_room") or {}
    if property_and_room.get("property_type") is not None:
        fields["filter__property_type"] = str(property_and_room["property_type"])
    if property_and_room.get("number_of_flatmates") is not None:
        fields["filter__number_of_flatmates"] = str(property_and_room["number_of_flatmates"])

    proximity = search.get("proximity_preferences") or {}
    if proximity.get("walking_distance") is not None:
        fields["filter__walking_distance"] = str(proximity["walking_distance"])
    if proximity.get("public_transport_time") is not None:
        fields["filter__public_transport_time"] = str(proximity["public_transport_time"])

    amenities = search.get("amenities") or {}
    for amenity_key in _AMENITY_KEYS:
        # Matches the New Search form's own checkbox semantics exactly: an
        # HTML checkbox either submits "on" (checked) or is entirely absent
        # (unchecked) — there is no third, explicit-"off" wire value. `False`
        # and `null` therefore both mean "no preference" here, the same as
        # they already do when a pilot operator leaves a checkbox unticked.
        if amenities.get(amenity_key) is True:
            fields[f"filter__{amenity_key}"] = "on"

    if search.get("feedback_mode") is not None:
        fields["feedback_mode"] = str(search["feedback_mode"])

    result_limits = search.get("result_limits") or {}
    if result_limits.get("max_result_count") is not None:
        fields["max_result_count"] = str(result_limits["max_result_count"])

    form = MultiDict(fields)

    connectors = search.get("connectors") or {}
    allowed_platform_ids = connectors.get("allowed_platform_ids")
    if allowed_platform_ids:
        form.setlist("enabled_platforms", [str(platform_id) for platform_id in allowed_platform_ids])

    return form


def parse_config_file(raw_content: str | bytes) -> dict:
    """Reads a config file's raw content (matching `config/pilot.example.json`'s
    shape) and returns exactly what `parse_search_form()` returns — the same
    dict `routes/search.py::submit_search()` already builds a job from.
    """
    if isinstance(raw_content, bytes):
        try:
            raw_content = raw_content.decode("utf-8")
        except UnicodeDecodeError:
            raise WebValidationError("Config file must be UTF-8 encoded") from None

    try:
        config = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise WebValidationError(f"Config file is not valid JSON: {exc}") from None

    if not isinstance(config, dict):
        raise WebValidationError("Config file must contain a JSON object")

    form = _translate_to_form_fields(config)
    return parse_search_form(form)
