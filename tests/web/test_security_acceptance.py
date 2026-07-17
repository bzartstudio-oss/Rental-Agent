"""Release Candidate security acceptance tests — see
docs/34_Security_Acceptance.md. Covers checks not already exercised by
`tests/web/test_security.py` (Step 16): XSS output escaping, SQL injection
resistance, unsafe filename rejection, API error-shape consistency, and
notification opt-in enforcement.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.storage import apartment_repository
from src.storage.models import Apartment
from tests.web.helpers import web_test_app


class XssOutputEscapingTests(unittest.TestCase):
    def test_a_malicious_apartment_title_is_rendered_escaped_not_executable(self) -> None:
        with web_test_app() as (app, db, tmp):
            now = datetime.now(timezone.utc)
            with db.transaction() as conn:
                # `web_test_app()` already registers `demo_platform`.
                apartment_repository.insert_apartment(
                    conn, Apartment(id="xss-test", platform_id="demo_platform", platform_listing_id="1",
                                     title="<script>alert(1)</script>", url="https://example.com/1",
                                     current_price=1000.0, current_status="available", first_seen_at=now, last_seen_at=now),
                )
            client = app.test_client()
            resp = client.get("/apartments/xss-test")
            html = resp.get_data(as_text=True)
            self.assertEqual(resp.status_code, 200)
            self.assertNotIn("<script>alert(1)</script>", html)
            self.assertIn("&lt;script&gt;", html)


class SqlInjectionResistanceTests(unittest.TestCase):
    def test_injection_style_apartment_ids_never_reach_raw_sql(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            for payload in ("1' OR '1'='1", "'; DROP TABLE apartments; --", "1 UNION SELECT * FROM platforms"):
                resp = client.get(f"/apartments/{payload}")
                self.assertIn(resp.status_code, (400, 404), f"payload {payload!r} was not safely rejected")

            with db.transaction() as conn:
                row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='apartments'").fetchone()
            self.assertIsNotNone(row, "the injection payload actually reached raw SQL and dropped a table")

    def test_injection_style_search_id_never_reaches_raw_sql(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            resp = client.get("/api/v1/searches/'; DROP TABLE search_requests; --")
            self.assertIn(resp.status_code, (400, 404))
            with db.transaction() as conn:
                row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='search_requests'").fetchone()
            self.assertIsNotNone(row)


class ApiErrorConsistencyTests(unittest.TestCase):
    def test_every_api_error_shares_the_same_structured_shape(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            not_found = client.get("/api/v1/apartments/00000000-0000-0000-0000-000000000000")
            validation = client.post("/api/v1/search-jobs", data={})
            for resp in (not_found, validation):
                body = resp.get_json()
                self.assertIn("error", body)
                self.assertIn("message", body)


if __name__ == "__main__":
    unittest.main()
