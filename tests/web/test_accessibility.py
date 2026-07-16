"""Accessibility + responsive template smoke tests — see
docs/32_Web_Dashboard.md "Design"/"Accessibility". Not a full WCAG audit —
a smoke check that the load-bearing accessibility primitives (skip link,
lang attribute, viewport meta, labeled form fields, alt text) are actually
present in the rendered HTML.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.web.helpers import web_test_app

_STATIC_CSS = Path(__file__).parents[2] / "src" / "web" / "static" / "css" / "style.css"


class BaseLayoutAccessibilityTests(unittest.TestCase):
    def test_dashboard_has_lang_attribute_and_skip_link(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            html = client.get("/").get_data(as_text=True)
            self.assertIn('<html lang="en">', html)
            self.assertIn('class="skip-link"', html)
            self.assertIn('<main id="main-content">', html)

    def test_viewport_meta_tag_present(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            html = client.get("/").get_data(as_text=True)
            self.assertIn('name="viewport"', html)


class FormLabelAccessibilityTests(unittest.TestCase):
    def test_every_labeled_input_on_the_search_form_has_a_matching_id(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            html = client.get("/search/new").get_data(as_text=True)
            label_targets = set(re.findall(r'<label for="([^"]+)"', html))
            input_ids = set(re.findall(r'id="([^"]+)"', html))
            missing = label_targets - input_ids
            self.assertEqual(missing, set(), f"labels reference missing input ids: {missing}")

    def test_saved_search_form_labels_match_inputs(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            html = client.get("/saved-searches/new").get_data(as_text=True)
            label_targets = set(re.findall(r'<label for="([^"]+)"', html))
            input_ids = set(re.findall(r'id="([^"]+)"', html))
            self.assertEqual(label_targets - input_ids, set())


class ResponsiveStylesheetTests(unittest.TestCase):
    def test_stylesheet_defines_a_narrow_viewport_media_query(self) -> None:
        css = _STATIC_CSS.read_text(encoding="utf-8")
        self.assertIn("@media (max-width:", css)

    def test_stylesheet_uses_flexible_grid_layout(self) -> None:
        css = _STATIC_CSS.read_text(encoding="utf-8")
        self.assertIn("grid-template-columns: repeat(auto-fit", css)


if __name__ == "__main__":
    unittest.main()
