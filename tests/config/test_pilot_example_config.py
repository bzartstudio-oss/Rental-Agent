"""Regression tests for `config/pilot.example.json` — Version 2.6 Milestone
2.6.1 (Pilot Materials Correctness). See
docs/38_Pilot_Feedback_pilot-valencia-01_2026-07-17.md's "Non-Blocking
Findings" #1-#3 and docs/41_Version_2.6_Planning.md.

Before this fix, the shipped example's budget (350-750 EUR) matched none of
the demo connector fixture prices (950-2600), and its `currency`/
`walking_distance`/`public_transport_time` values unconditionally zeroed out
every demo result (demo connectors never populate `Apartment.currency` or
coordinates). These tests prove the corrected example actually produces
results against the real demo connectors — not just that the JSON parses.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from src.storage import apartment_repository
from tests.acceptance.helpers import acceptance_app, csrf_token_from, wait_for_job

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "pilot.example.json"


def _load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _form_from_config(config: dict, csrf_token: str) -> dict:
    """Translates the config's shape into web form fields exactly the way
    docs/37_Pilot_Operations_Guide.md section 9 instructs a pilot operator
    to do by hand: a null value means the field is left blank (omitted),
    not submitted as a literal "null" or "None" string.
    """
    search = config["search"]
    form = {
        "csrf_token": csrf_token,
        "country": search["location"]["country"],
        "region": search["location"]["region"],
        "city": search["location"]["city"],
        "postal_area": search["location"]["postal_area"],
        "filter__min_price": str(search["budget"]["min_price"]),
        "filter__max_price": str(search["budget"]["max_price"]),
        "feedback_mode": search["feedback_mode"],
    }
    if search["budget"]["currency"] is not None:
        form["filter__currency"] = search["budget"]["currency"]
    if search["proximity_preferences"]["walking_distance"] is not None:
        form["filter__walking_distance"] = str(search["proximity_preferences"]["walking_distance"])
    if search["proximity_preferences"]["public_transport_time"] is not None:
        form["filter__public_transport_time"] = str(search["proximity_preferences"]["public_transport_time"])
    for amenity_key in ("internet_included", "furnished"):
        if search["amenities"][amenity_key] is True:
            form[f"filter__{amenity_key}"] = "on"
    return form


class PilotExampleConfigValuesTests(unittest.TestCase):
    """Static checks on the JSON itself — fast, no server needed."""

    def test_config_is_valid_json(self) -> None:
        _load_config()  # raises if malformed

    def test_budget_is_internally_consistent(self) -> None:
        budget = _load_config()["search"]["budget"]
        self.assertLess(budget["min_price"], budget["max_price"])

    def test_budget_covers_actual_demo_fixture_price_range(self) -> None:
        # The demo connector fixtures' own real, deterministic prices (see
        # src/connectors/fixtures/demo_platform*/listings.html) — confirmed
        # via direct database query during the pilot session that found
        # this bug. Not re-derived from the connector at test time to keep
        # this a fast, static check; the end-to-end test below proves the
        # live behavior.
        known_fixture_prices = (950.0, 1050.0, 1100.0, 1450.0, 2100.0, 2600.0)
        budget = _load_config()["search"]["budget"]
        for price in known_fixture_prices:
            self.assertGreaterEqual(price, budget["min_price"], f"{price} below example min_price")
            self.assertLessEqual(price, budget["max_price"], f"{price} above example max_price")

    def test_currency_and_proximity_filters_are_left_unset(self) -> None:
        """These three fields must stay null: demo connectors never populate
        currency or coordinates, so any non-null value here unconditionally
        zeroes out every demo result (see docs/38 pilot feedback #2/#3).
        """
        search = _load_config()["search"]
        self.assertIsNone(search["budget"]["currency"])
        self.assertIsNone(search["proximity_preferences"]["walking_distance"])
        self.assertIsNone(search["proximity_preferences"]["public_transport_time"])


class PilotExampleConfigEndToEndTests(unittest.TestCase):
    """Real Flask app, real demo connectors, real search — proves the
    corrected example config produces actual usable results, not just
    internally-consistent numbers.
    """

    def test_config_values_produce_nonzero_demo_results(self) -> None:
        config = _load_config()
        with acceptance_app() as (app, db, tmp):
            client = app.test_client()
            resp = client.get("/search/new")
            token = csrf_token_from(resp.get_data(as_text=True))
            form = _form_from_config(config, token)

            resp = client.post("/search/new", data=form, follow_redirects=False)
            self.assertEqual(resp.status_code, 302, resp.get_data(as_text=True)[:1000])
            job = wait_for_job(client, resp.headers["Location"])
            self.assertIn(job["status"], ("completed", "partial"), job)

            search_id = job["result_reference"]
            resp = client.get(f"/search/results/{search_id}")
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            apartment_ids = list(dict.fromkeys(re.findall(r"/apartments/([a-f0-9\-]+)", html)))
            self.assertTrue(apartment_ids, "corrected pilot config produced zero results against demo connectors")

            budget = config["search"]["budget"]
            with db.transaction() as conn:
                for apartment_id in apartment_ids:
                    apartment = apartment_repository.get_apartment(conn, apartment_id)
                    self.assertGreaterEqual(apartment.current_price, budget["min_price"])
                    self.assertLessEqual(apartment.current_price, budget["max_price"])


if __name__ == "__main__":
    unittest.main()
