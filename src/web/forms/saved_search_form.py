"""Saved Search create/edit form — see docs/32_Web_Dashboard.md "Saved-Search
Workflow". Reuses `search_form.parse_search_form()` for the underlying
request/criteria — a saved search's definition is the same shape a one-off
search already validates, plus a name/description/monitoring destinations.
"""

from __future__ import annotations

from src.web.forms.search_form import parse_search_form
from src.web.forms.validation import parse_bool, require_text


def parse_saved_search_form(form) -> dict:
    search_fields = parse_search_form(form)
    name = require_text(form.get("name"), "Saved search name")

    destinations = []
    if form.get("destination_country") or form.get("destination_city"):
        destinations.append({
            "country": form.get("destination_country") or None,
            "region": form.get("destination_region") or None,
            "city": form.get("destination_city") or None,
        })

    return {
        "name": name,
        "description": form.get("description") or None,
        "location": search_fields["location"],
        "criteria": search_fields["criteria"],
        "enable_monitoring": parse_bool(form.get("enable_monitoring", "on")),
        "geographic_destinations": destinations,
    }
