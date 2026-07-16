"""HTML route tests — see docs/32_Web_Dashboard.md "Route Structure".

Verifies every GET route renders, 404s use the real template (not a raw
traceback), and results/apartment-detail pages actually reflect a real
completed search — never SQL in a route, only facade calls.
"""

from __future__ import annotations

import re
import time
import unittest

from src.web.constants import TERMINAL_JOB_STATUSES
from src.web.jobs import service as jobs_service
from tests.web.helpers import csrf_token_from, web_test_app


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


if __name__ == "__main__":
    unittest.main()
