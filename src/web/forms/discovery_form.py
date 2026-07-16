"""Manual Platform Discovery form — see docs/32_Web_Dashboard.md "Discovery
Workflow".
"""

from __future__ import annotations

from src.web.error_handler import WebValidationError
from src.web.forms.validation import parse_checkbox_list


def parse_discovery_form(form) -> dict:
    country = form.get("country") or None
    city = form.get("city") or None
    if not country and not city:
        raise WebValidationError("At least a country or a city is required")
    return {
        "country": country, "region": form.get("region") or None, "city": city,
        "rental_categories": parse_checkbox_list(form.getlist("rental_categories")),
    }
