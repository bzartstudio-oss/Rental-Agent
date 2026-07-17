"""Form validation tests — see docs/32_Web_Dashboard.md "Validation"."""

from __future__ import annotations

import json
import unittest
from werkzeug.datastructures import MultiDict

from src.web.error_handler import WebValidationError
from src.web.forms.config_loader import parse_config_file
from src.web.forms.discovery_form import parse_discovery_form
from src.web.forms.feedback_form import parse_feedback_form
from src.web.forms.notification_form import parse_notification_preference_form
from src.web.forms.search_form import parse_search_form
from src.web.forms.validation import (
    parse_optional_float,
    parse_optional_int,
    parse_result_limit,
    parse_safe_id,
    parse_safe_url,
)


class ValidationHelperTests(unittest.TestCase):
    def test_parse_safe_id_rejects_path_traversal(self) -> None:
        with self.assertRaises(WebValidationError):
            parse_safe_id("../../etc/passwd", "id")

    def test_parse_safe_id_rejects_slash(self) -> None:
        with self.assertRaises(WebValidationError):
            parse_safe_id("abc/def", "id")

    def test_parse_safe_id_accepts_uuid(self) -> None:
        self.assertEqual(parse_safe_id("a1b2c3d4-0000-0000-0000-000000000000", "id"), "a1b2c3d4-0000-0000-0000-000000000000")

    def test_parse_optional_float_rejects_non_numeric(self) -> None:
        with self.assertRaises(WebValidationError):
            parse_optional_float("not-a-number", "field")

    def test_parse_optional_float_rejects_negative_price(self) -> None:
        with self.assertRaises(WebValidationError):
            parse_optional_float("-500", "Max price", minimum=0.0)

    def test_parse_optional_int_rejects_out_of_range(self) -> None:
        with self.assertRaises(WebValidationError):
            parse_optional_int("500", "Max results", maximum=200)

    def test_parse_result_limit_rejects_excessive_value(self) -> None:
        with self.assertRaises(WebValidationError):
            parse_result_limit("100000")

    def test_parse_result_limit_defaults_when_absent(self) -> None:
        self.assertEqual(parse_result_limit(None, default=50), 50)

    def test_parse_safe_url_rejects_javascript_scheme(self) -> None:
        with self.assertRaises(WebValidationError):
            parse_safe_url("javascript:alert(1)", "URL")

    def test_parse_safe_url_rejects_file_scheme(self) -> None:
        with self.assertRaises(WebValidationError):
            parse_safe_url("file:///etc/passwd", "URL")

    def test_parse_safe_url_accepts_https(self) -> None:
        self.assertEqual(parse_safe_url("https://example.com/listing/1", "URL"), "https://example.com/listing/1")


class SearchFormTests(unittest.TestCase):
    def test_requires_a_location(self) -> None:
        with self.assertRaises(WebValidationError):
            parse_search_form(MultiDict({}))

    def test_accepts_city_country_combo(self) -> None:
        fields = parse_search_form(MultiDict({"city": "Valencia", "country": "Spain"}))
        self.assertIn("Valencia", fields["location"])
        self.assertIn("Spain", fields["location"])

    def test_boolean_filter_field_parses_checkbox(self) -> None:
        form = MultiDict({"city": "Valencia", "filter__private_bathroom": "on"})
        fields = parse_search_form(form)
        self.assertTrue(fields["criteria"].get("private_bathroom"))

    def test_number_filter_field_rejects_negative(self) -> None:
        form = MultiDict({"city": "Valencia", "filter__max_price": "-100"})
        with self.assertRaises(WebValidationError):
            parse_search_form(form)

    def test_max_result_count_is_capped(self) -> None:
        form = MultiDict({"city": "Valencia", "max_result_count": "999999"})
        with self.assertRaises(WebValidationError):
            parse_search_form(form)


class ConfigLoaderTests(unittest.TestCase):
    """v2.6 Milestone 2.6.3 — see docs/41_Version_2.6_Planning.md and
    src/web/forms/config_loader.py's own docstring. `parse_config_file()`
    must reuse `parse_search_form()`'s validation, not reimplement it — every
    test here proves that reuse, not new validation logic.
    """

    def _valid_config(self, **overrides) -> dict:
        config = {
            "search": {
                "location": {"country": "Spain", "region": None, "city": "Valencia", "postal_area": None},
                "budget": {"currency": None, "min_price": 900, "max_price": 2700},
                "property_and_room": {"property_type": None, "room_type": None, "number_of_rooms": None, "number_of_flatmates": None},
                "proximity_preferences": {"walking_distance": None, "public_transport_time": None},
                "amenities": {
                    "internet_included": True, "furnished": False, "private_bathroom": None,
                    "air_conditioning": None, "heating": None, "elevator": None, "pets_allowed": None,
                },
                "feedback_mode": "suggested",
                "connectors": {"allowed_platform_ids": ["demo_platform"]},
                "result_limits": {"max_result_count": 10},
            }
        }
        config["search"].update(overrides)
        return config

    def test_valid_config_produces_the_same_shape_parse_search_form_does(self) -> None:
        fields = parse_config_file(json.dumps(self._valid_config()))
        self.assertIn("Valencia", fields["location"])
        self.assertIn("Spain", fields["location"])
        self.assertEqual(fields["criteria"]["min_price"], 900.0)
        self.assertEqual(fields["criteria"]["max_price"], 2700.0)
        self.assertTrue(fields["criteria"]["internet_included"])
        self.assertNotIn("furnished", fields["criteria"])  # False -> "no preference", not an explicit exclusion
        self.assertEqual(fields["allowed_platform_ids"], ["demo_platform"])
        self.assertEqual(fields["feedback_mode"], "suggested")

    def test_number_of_rooms_and_room_type_are_never_translated(self) -> None:
        """Regression for a real defect found while verifying this milestone:
        `property_and_room.number_of_rooms` looks like it should map to the
        registered `number_of_rooms` filter, but that filter is an exact
        total-bedroom-count match, not "how many rooms the pilot user needs"
        — auto-mapping it produced zero results against every demo fixture
        apartment (see src/web/forms/config_loader.py's module docstring).
        """
        config = self._valid_config(
            property_and_room={"property_type": None, "room_type": "private_room", "number_of_rooms": 1, "number_of_flatmates": None},
        )
        fields = parse_config_file(json.dumps(config))
        self.assertNotIn("number_of_rooms", fields["criteria"])
        self.assertNotIn("room_type", fields["criteria"])

    def test_malformed_json_is_rejected(self) -> None:
        with self.assertRaises(WebValidationError):
            parse_config_file("{not valid json")

    def test_a_json_array_instead_of_an_object_is_rejected(self) -> None:
        with self.assertRaises(WebValidationError):
            parse_config_file("[1, 2, 3]")

    def test_missing_search_key_is_rejected(self) -> None:
        with self.assertRaises(WebValidationError):
            parse_config_file(json.dumps({"not_search": {}}))

    def test_config_missing_a_location_is_rejected_the_same_way_a_form_would_be(self) -> None:
        config = self._valid_config(location={"country": None, "region": None, "city": None, "postal_area": None})
        with self.assertRaises(WebValidationError):
            parse_config_file(json.dumps(config))

    def test_out_of_range_price_is_rejected_the_same_way_a_form_would_be(self) -> None:
        config = self._valid_config(budget={"currency": None, "min_price": -100, "max_price": 2700})
        with self.assertRaises(WebValidationError):
            parse_config_file(json.dumps(config))

    def test_bytes_content_is_accepted(self) -> None:
        fields = parse_config_file(json.dumps(self._valid_config()).encode("utf-8"))
        self.assertIn("Valencia", fields["location"])

    def test_the_shipped_pilot_example_config_loads_without_error(self) -> None:
        from pathlib import Path

        config_path = Path(__file__).resolve().parents[2] / "config" / "pilot.example.json"
        fields = parse_config_file(config_path.read_text(encoding="utf-8"))
        self.assertTrue(fields["location"])


class DiscoveryFormTests(unittest.TestCase):
    def test_requires_country_or_city(self) -> None:
        with self.assertRaises(WebValidationError):
            parse_discovery_form(MultiDict({}))

    def test_accepts_city_only(self) -> None:
        fields = parse_discovery_form(MultiDict({"city": "Valencia"}))
        self.assertEqual(fields["city"], "Valencia")


class FeedbackFormTests(unittest.TestCase):
    def test_rejects_unknown_event_type(self) -> None:
        with self.assertRaises(WebValidationError):
            parse_feedback_form(MultiDict({"event_type": "not_a_real_event_type"}))

    def test_accepts_known_event_type(self) -> None:
        fields = parse_feedback_form(MultiDict({"event_type": "shortlisted"}))
        self.assertEqual(fields["event_type"], "shortlisted")

    def test_rejects_unsafe_apartment_id(self) -> None:
        with self.assertRaises(WebValidationError):
            parse_feedback_form(MultiDict({"event_type": "viewed", "apartment_id": "../../etc/passwd"}))


class NotificationFormTests(unittest.TestCase):
    def test_requires_at_least_one_channel(self) -> None:
        with self.assertRaises(WebValidationError):
            parse_notification_preference_form(MultiDict({}))

    def test_rejects_unknown_channel(self) -> None:
        form = MultiDict()
        form.setlist("enabled_channels", ["not_a_real_channel"])
        with self.assertRaises(WebValidationError):
            parse_notification_preference_form(form)

    def test_rejects_invalid_quiet_hours_format(self) -> None:
        form = MultiDict()
        form.setlist("enabled_channels", ["console"])
        form["quiet_hours_start"] = "not-a-time"
        with self.assertRaises(WebValidationError):
            parse_notification_preference_form(form)

    def test_accepts_valid_console_preference(self) -> None:
        form = MultiDict()
        form.setlist("enabled_channels", ["console"])
        fields = parse_notification_preference_form(form)
        self.assertEqual(fields["enabled_channels"], ["console"])


if __name__ == "__main__":
    unittest.main()
