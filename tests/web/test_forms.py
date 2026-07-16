"""Form validation tests — see docs/32_Web_Dashboard.md "Validation"."""

from __future__ import annotations

import unittest
from werkzeug.datastructures import MultiDict

from src.web.error_handler import WebValidationError
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
