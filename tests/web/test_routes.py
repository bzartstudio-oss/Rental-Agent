"""HTML route tests — see docs/32_Web_Dashboard.md "Route Structure".

Verifies every GET route renders, 404s use the real template (not a raw
traceback), and results/apartment-detail pages actually reflect a real
completed search — never SQL in a route, only facade calls.
"""

from __future__ import annotations

import io
import re
import time
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.geography.history import record_geo_enrichment
from src.geography.models import GeoEnrichment, GeoResult, TravelMode
from src.storage import apartment_repository
from src.storage.models import Apartment
from src.web.constants import TERMINAL_JOB_STATUSES
from src.web.jobs import service as jobs_service
from tests.web.helpers import csrf_token_from, web_test_app

_PILOT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "pilot.example.json"


def _run_a_real_search(client, db):
    resp = client.get("/search/new")
    token = csrf_token_from(resp.get_data(as_text=True))
    resp = client.post("/search/new", data={"csrf_token": token, "city": "Example City"}, follow_redirects=False)
    job_url = resp.headers["Location"]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        resp = client.get(job_url, headers={"Accept": "application/json"})
        job = resp.get_json()["job"]
        if job["status"] in TERMINAL_JOB_STATUSES:
            return job
        time.sleep(0.2)
    raise TimeoutError("search never completed")


class StaticPageTests(unittest.TestCase):
    def test_every_top_level_page_renders(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            for route in ("/", "/search/new", "/saved-searches", "/saved-searches/new", "/monitoring",
                          "/notifications", "/notifications/preferences/new", "/discovery", "/preferences", "/health"):
                resp = client.get(route)
                self.assertEqual(resp.status_code, 200, f"{route} -> {resp.status_code}")

    def test_unknown_apartment_returns_404_page(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            resp = client.get("/apartments/00000000-0000-0000-0000-000000000000")
            self.assertEqual(resp.status_code, 404)
            self.assertIn("not found", resp.get_data(as_text=True).lower())

    def test_unknown_saved_search_returns_404(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            resp = client.get("/saved-searches/00000000-0000-0000-0000-000000000000")
            self.assertEqual(resp.status_code, 404)


class SearchResultsPageTests(unittest.TestCase):
    def test_results_page_shows_original_listing_urls(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            job = _run_a_real_search(client, db)
            self.assertIn(job["status"], ("completed", "partial"))
            resp = client.get(f"/search/results/{job['result_reference']}")
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn("Original listing", html)
            self.assertRegex(html, r'href="https?://')

    def test_apartment_detail_page_shows_original_url(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            job = _run_a_real_search(client, db)
            resp = client.get(f"/search/results/{job['result_reference']}")
            apartment_id = re.search(r"/apartments/([a-f0-9\-]+)", resp.get_data(as_text=True)).group(1)
            resp = client.get(f"/apartments/{apartment_id}")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("Original listing", resp.get_data(as_text=True))


class ApartmentImageServingTests(unittest.TestCase):
    """A demo/fixture connector's `ApartmentImage.source_url` is a `file://`
    path (see `src/connectors/demo_platform.py`) — no real browser will ever
    load that from an `http://` page (and this platform's own CSP already
    assumes same-origin image serving, see `security.py`). The detail page
    must render the already-downloaded local copy through a real same-origin
    route instead of the raw `file://` source_url.
    """

    def test_detail_page_never_renders_a_file_url_for_images(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            job = _run_a_real_search(client, db)
            resp = client.get(f"/search/results/{job['result_reference']}")
            apartment_id = re.search(r"/apartments/([a-f0-9\-]+)", resp.get_data(as_text=True)).group(1)
            resp = client.get(f"/apartments/{apartment_id}")
            html = resp.get_data(as_text=True)
            self.assertNotIn('src="file://', html)

    def test_apartment_media_route_serves_the_downloaded_image_bytes(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            job = _run_a_real_search(client, db)
            resp = client.get(f"/search/results/{job['result_reference']}")
            apartment_id = re.search(r"/apartments/([a-f0-9\-]+)", resp.get_data(as_text=True)).group(1)
            resp = client.get(f"/apartments/{apartment_id}")
            html = resp.get_data(as_text=True)
            media_url = re.search(r'src="(/apartments/[a-f0-9\-]+/media/[^"]+)"', html)
            self.assertIsNotNone(media_url, "no same-origin media URL found in the rendered image gallery")
            image_resp = client.get(media_url.group(1))
            self.assertEqual(image_resp.status_code, 200)
            self.assertGreater(len(image_resp.get_data()), 0)
            self.assertTrue(image_resp.content_type.startswith("image/"))

    def test_media_route_rejects_path_traversal(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            job = _run_a_real_search(client, db)
            resp = client.get(f"/search/results/{job['result_reference']}")
            apartment_id = re.search(r"/apartments/([a-f0-9\-]+)", resp.get_data(as_text=True)).group(1)
            resp = client.get(f"/apartments/{apartment_id}/media/..%2F..%2F..%2Fetc%2Fpasswd")
            self.assertEqual(resp.status_code, 404)

    def test_media_route_404s_for_unknown_filename(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            job = _run_a_real_search(client, db)
            resp = client.get(f"/search/results/{job['result_reference']}")
            apartment_id = re.search(r"/apartments/([a-f0-9\-]+)", resp.get_data(as_text=True)).group(1)
            resp = client.get(f"/apartments/{apartment_id}/media/does-not-exist.png")
            self.assertEqual(resp.status_code, 404)


class ApartmentGeographicAnalysisRenderingTests(unittest.TestCase):
    """Version 2.6 Milestone 2.6.1 — see
    docs/38_Pilot_Feedback_pilot-valencia-01_2026-07-17.md finding #5:
    the detail page used to render `entry.summary`'s raw Python dict repr
    (e.g. `{'distances': {}, 'nearby': {}}`) whenever no real geographic
    data existed, instead of a clean message.
    """

    def _insert_apartment(self, conn, now) -> str:
        apartment_id = str(uuid.uuid4())
        apartment_repository.insert_apartment(
            conn,
            Apartment(
                id=apartment_id, platform_id="demo_platform", platform_listing_id=apartment_id,
                title="Test Apartment", url="https://example.com/listings/test-geo",
                current_price=1000.0, current_status="available", first_seen_at=now, last_seen_at=now,
            ),
        )
        return apartment_id

    def test_empty_geo_analysis_renders_clean_message_not_raw_dict(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            now = datetime.now(timezone.utc)
            with db.transaction() as conn:
                apartment_id = self._insert_apartment(conn, now)
                # No coordinates -> the real GeographicEngine would produce
                # exactly this: an enrichment with empty distances/nearby.
                record_geo_enrichment(conn, GeoEnrichment(apartment_id=apartment_id), now)

            resp = client.get(f"/apartments/{apartment_id}")
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn("Not available", html)
            self.assertNotIn("{'distances'", html)
            self.assertNotIn("{&#39;distances&#39;", html)

    def test_populated_geo_analysis_still_renders_real_data(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            now = datetime.now(timezone.utc)
            with db.transaction() as conn:
                apartment_id = self._insert_apartment(conn, now)
                result = GeoResult(
                    origin=(0, 0), destination=(0, 1), mode=TravelMode.WALKING, distance_km=2.5,
                    travel_time_minutes=30.0, confidence=0.7, computed_at=now,
                    provider_id="haversine", calculation_method="haversine",
                )
                enrichment = GeoEnrichment(apartment_id=apartment_id, distances={TravelMode.WALKING: result})
                record_geo_enrichment(conn, enrichment, now)

            resp = client.get(f"/apartments/{apartment_id}")
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn("Computed via haversine", html)
            self.assertIn("distances", html)
            self.assertNotIn("Not available — no distances", html)


class JobPageRefreshTests(unittest.TestCase):
    def test_job_status_survives_a_simulated_page_refresh(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            resp = client.get("/search/new")
            token = csrf_token_from(resp.get_data(as_text=True))
            resp = client.post("/search/new", data={"csrf_token": token, "city": "Example City"}, follow_redirects=False)
            job_url = resp.headers["Location"]

            # First "load" of the job page.
            first = client.get(job_url)
            self.assertEqual(first.status_code, 200)
            # A second, independent GET (simulating a browser refresh) must
            # still resolve — the job is read fresh from the database each
            # time, not held only in server memory.
            second = client.get(job_url)
            self.assertEqual(second.status_code, 200)

            # Wait for the background job thread to finish before the
            # `web_test_app()` context tears down its temp database out from
            # under it — otherwise the still-running thread's next
            # `Database.transaction()` call raises (harmlessly, but noisily)
            # once the temp directory is gone.
            job_id = job_url.rsplit("/", 1)[-1]
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                status_resp = client.get(job_url, headers={"Accept": "application/json"})
                if status_resp.get_json()["job"]["status"] in TERMINAL_JOB_STATUSES:
                    break
                time.sleep(0.2)


class ConfigFileUploadTests(unittest.TestCase):
    """v2.6 Milestone 2.6.3 — see docs/41_Version_2.6_Planning.md and
    src/web/forms/config_loader.py. Proves the real, shipped
    config/pilot.example.json can be uploaded through the real `/search/new`
    route and drive a real demo search — not just that the loader function
    parses it in isolation (already proven in tests/web/test_forms.py).
    """

    def test_uploading_the_shipped_pilot_config_starts_a_real_search(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            resp = client.get("/search/new")
            token = csrf_token_from(resp.get_data(as_text=True))

            config_bytes = _PILOT_CONFIG_PATH.read_bytes()
            resp = client.post(
                "/search/new",
                data={"csrf_token": token, "config_file": (io.BytesIO(config_bytes), "pilot.example.json")},
                content_type="multipart/form-data",
                follow_redirects=False,
            )
            self.assertEqual(resp.status_code, 302, resp.get_data(as_text=True)[:1000])
            job_url = resp.headers["Location"]

            deadline = time.monotonic() + 30
            job = None
            while time.monotonic() < deadline:
                resp = client.get(job_url, headers={"Accept": "application/json"})
                job = resp.get_json()["job"]
                if job["status"] in TERMINAL_JOB_STATUSES:
                    break
                time.sleep(0.2)
            self.assertIn(job["status"], ("completed", "partial"), job)

            resp = client.get(f"/search/results/{job['result_reference']}")
            html = resp.get_data(as_text=True)
            apartment_ids = re.findall(r"/apartments/([a-f0-9\-]+)", html)
            self.assertTrue(apartment_ids, "uploading the shipped pilot config produced zero results")

    def test_submitting_without_a_config_file_still_uses_the_manual_form_fields(self) -> None:
        """Regression: the existing manual-entry path (no file uploaded) must
        keep working exactly as before — the config-file upload is additive.
        """
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            job = _run_a_real_search(client, db)
            self.assertIn(job["status"], ("completed", "partial"))


if __name__ == "__main__":
    unittest.main()
