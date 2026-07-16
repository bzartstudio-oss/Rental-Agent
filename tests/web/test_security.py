"""Security tests — CSRF, path traversal, security headers, secret
redaction, request-size limits. See docs/32_Web_Dashboard.md "Security
Model".
"""

from __future__ import annotations

import unittest
from pathlib import Path

from src.web.security import WebSecurity
from tests.web.helpers import csrf_token_from, web_test_app


class SafeJoinTests(unittest.TestCase):
    def test_rejects_escape_above_base_dir(self) -> None:
        base = Path(__file__).parent
        result = WebSecurity.safe_join(base, "..", "..", "..", "etc", "passwd")
        self.assertIsNone(result)

    def test_allows_a_real_file_under_base_dir(self) -> None:
        base = Path(__file__).parent
        result = WebSecurity.safe_join(base, "test_security.py")
        self.assertIsNotNone(result)
        self.assertTrue(str(result).endswith("test_security.py"))


class SafeUrlTests(unittest.TestCase):
    def test_rejects_javascript_scheme(self) -> None:
        self.assertFalse(WebSecurity.is_safe_url("javascript:alert(1)"))

    def test_rejects_data_scheme(self) -> None:
        self.assertFalse(WebSecurity.is_safe_url("data:text/html,<script>1</script>"))

    def test_accepts_https(self) -> None:
        self.assertTrue(WebSecurity.is_safe_url("https://example.com/x"))


class CsrfProtectionTests(unittest.TestCase):
    def test_post_without_token_is_rejected(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            resp = client.post("/preferences/record", data={"event_type": "viewed"})
            self.assertEqual(resp.status_code, 400)

    def test_post_with_wrong_token_is_rejected(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            client.get("/search/new")  # establishes a session + real token
            resp = client.post("/preferences/record", data={"csrf_token": "wrong-token", "event_type": "viewed"})
            self.assertEqual(resp.status_code, 400)

    def test_post_with_valid_token_is_accepted(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            resp = client.get("/notifications/preferences/new")
            token = csrf_token_from(resp.get_data(as_text=True))
            form = {"csrf_token": token, "enabled_channels": ["console"]}
            resp = client.post("/notifications/preferences/new", data=form)
            self.assertEqual(resp.status_code, 302)

    def test_get_requests_never_require_csrf(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            resp = client.get("/")
            self.assertEqual(resp.status_code, 200)

    def test_api_routes_are_exempt_from_csrf(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            resp = client.get("/api/v1/health")
            self.assertEqual(resp.status_code, 200)


class SecurityHeaderTests(unittest.TestCase):
    def test_every_response_carries_hardening_headers(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            resp = client.get("/")
            self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")
            self.assertEqual(resp.headers.get("Referrer-Policy"), "no-referrer")
            self.assertIn("default-src 'self'", resp.headers.get("Content-Security-Policy", ""))


class PathTraversalRouteTests(unittest.TestCase):
    def test_malformed_apartment_id_is_rejected(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            resp = client.get("/apartments/" + ".." + ".." + "etc")
            self.assertEqual(resp.status_code, 400)


class RequestSizeLimitTests(unittest.TestCase):
    def test_oversized_request_body_is_rejected(self) -> None:
        with web_test_app() as (app, db, tmp):
            app.config["MAX_CONTENT_LENGTH"] = 100
            client = app.test_client()
            resp = client.get("/search/new")
            token = csrf_token_from(resp.get_data(as_text=True))
            resp = client.post("/search/new", data={"csrf_token": token, "city": "x" * 1000})
            self.assertEqual(resp.status_code, 413)


class SecretRedactionTests(unittest.TestCase):
    def test_channel_config_status_never_exposes_secrets(self) -> None:
        with web_test_app() as (app, db, tmp):
            with app.app_context():
                from src.web.application import get_facade

                channels = get_facade().channel_config_status()
            for channel in channels:
                self.assertFalse(hasattr(channel, "password"))
                self.assertFalse(hasattr(channel, "signing_secret"))


class LocalhostBindingTests(unittest.TestCase):
    def test_default_configuration_binds_localhost_only(self) -> None:
        from src.web.configuration import WebConfiguration

        configuration = WebConfiguration()
        self.assertEqual(configuration.host, "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
