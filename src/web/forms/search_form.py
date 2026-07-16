"""New Search Workflow form — see docs/32_Web_Dashboard.md "Search Workflow".

The dynamic filter section (property/location/amenities/price/platform/media)
is built entirely from `FilterRegistry.all()` — see `available_filters()` on
the facade — so this module never hand-codes a duplicate filter's validation;
it only turns `filter__<key>` fields into the flat criteria dict
`SearchRequest.criteria`/`FilterEngine.run()` already expect (each filter's
own `validate()` runs again downstream at `SearchRequest` construction, the
same "fail fast, but the filter itself is still the one source of truth for
what's valid" reasoning `search.criteria.validate_criteria()` already applies).
"""

from __future__ import annotations

from src.filter_engine.registry import FilterRegistry
from src.web.error_handler import WebValidationError
from src.web.forms.validation import (
    parse_bool,
    parse_checkbox_list,
    parse_optional_float,
    parse_ranking_weights,
    parse_result_limit,
    require_text,
)


def parse_search_form(form) -> dict:
    location_parts = [
        form.get("country", "").strip(), form.get("region", "").strip(),
        form.get("city", "").strip(), form.get("postal_area", "").strip(),
    ]
    location = ", ".join(part for part in location_parts if part) or form.get("location", "").strip()
    if not location:
        raise WebValidationError("At least a city or a location is required")

    criteria: dict = {}
    for base_filter in FilterRegistry.all():
        field_name = f"filter__{base_filter.key}"
        if field_name not in form or form.get(field_name) in (None, ""):
            continue
        metadata = base_filter.metadata()
        raw = form.get(field_name)
        if metadata.value_type == "boolean":
            criteria[base_filter.key] = parse_bool(raw)
        elif metadata.value_type == "number":
            value = parse_optional_float(raw, metadata.display_name, minimum=0.0)
            if value is not None:
                criteria[base_filter.key] = value
        else:
            criteria[base_filter.key] = raw

    return {
        "location": location,
        "criteria": criteria,
        "label": form.get("label") or None,
        "use_filter_engine": parse_bool(form.get("use_filter_engine")) or bool(criteria),
        "use_geo_engine": parse_bool(form.get("use_geo_engine", "on")),
        "ranking_weights": parse_ranking_weights(form) if form.get("ranking_profile") == "custom" else None,
        "feedback_mode": form.get("feedback_mode") or None,
        "allowed_platform_ids": parse_checkbox_list(form.getlist("enabled_platforms")) or None,
        "max_results": parse_result_limit(form.get("max_result_count")),
        "save_search": parse_bool(form.get("save_search")),
        "enable_monitoring": parse_bool(form.get("enable_monitoring")),
        "saved_search_name": form.get("saved_search_name") or None,
    }
