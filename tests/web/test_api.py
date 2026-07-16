"""JSON API v1 tests — see docs/32_Web_Dashboard.md "API Structure"."""

from __future__ import annotations

import time
import unittest

from src.web.constants import TERMINAL_JOB_STATUSES
from tests.web.helpers import csrf_token_from, web_test_app


class ApiHealthTests(unittest.TestCase):
    def test_health_endpoint_returns_structured_json(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            resp = client.get("/api/v1/health")
            self.assertEqual(resp.status_code, 200)
            body = resp.get_json()
            self.assertIn("health", body)
            self.assertIn("statistics", body)


class ApiSearchJobTests(unittest.TestCase):
    def test_create_and_poll_a_search_job(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            resp = client.post("/api/v1/search-jobs", data={"city": "Example City"})
            self.assertEqual(resp.status_code, 202)
            job_id = resp.get_json()["job"]["job_id"]

            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                resp = client.get(f"/api/v1/search-jobs/{job_id}")
                job = resp.get_json()["job"]
                if job["status"] in TERMINAL_JOB_STATUSES:
                    break
                time.sleep(0.2)
            self.assertIn(job["status"], ("completed", "partial"))

            resp = client.get(f"/api/v1/searches/{job['result_reference']}")
            self.assertEqual(resp.status_code, 200)
            body = resp.get_json()
            self.assertTrue(body["entries"])
            self.assertTrue(body["apartments"])


class ApiValidationErrorTests(unittest.TestCase):
    def test_missing_location_returns_structured_400(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            resp = client.post("/api/v1/search-jobs", data={})
            self.assertEqual(resp.status_code, 400)
            body = resp.get_json()
            self.assertEqual(body["error"], "validation_error")


class ApiNotFoundTests(unittest.TestCase):
    def test_unknown_apartment_returns_structured_404(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            resp = client.get("/api/v1/apartments/00000000-0000-0000-0000-000000000000")
            self.assertEqual(resp.status_code, 404)
            body = resp.get_json()
            self.assertEqual(body["error"], "not_found")


class ApiListingEndpointTests(unittest.TestCase):
    def test_saved_searches_platforms_and_discovery_endpoints_respond(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            for route in ("/api/v1/saved-searches", "/api/v1/platforms", "/api/v1/discovery-runs",
                          "/api/v1/discovery-runs/candidates", "/api/v1/monitoring-events",
                          "/api/v1/notifications/preferences", "/api/v1/notifications/deliveries",
                          "/api/v1/notifications/channels", "/api/v1/preferences", "/api/v1/feedback/history"):
                resp = client.get(route)
                self.assertEqual(resp.status_code, 200, f"{route} -> {resp.status_code}: {resp.get_data(as_text=True)[:300]}")
                self.assertTrue(resp.is_json)


if __name__ == "__main__":
    unittest.main()
