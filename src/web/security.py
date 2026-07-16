"""`WebSecurity` — CSRF protection, security headers, safe file serving, and
URL validation for the web layer. See docs/32_Web_Dashboard.md "Security
Model".

No extra dependency (`flask-wtf` etc.) — a session-stored random token
compared against the submitted form field is the entire mechanism, matching
"do not introduce a heavy frontend framework unless clearly justified."
"""

from __future__ import annotations

import secrets
from pathlib import Path
from urllib.parse import urlparse

from flask import Request, Response, session

CSRF_SESSION_KEY = "_csrf_token"
CSRF_FORM_FIELD = "csrf_token"
_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


class CsrfValidationError(Exception):
    """Raised for a missing/mismatched CSRF token on a state-changing request."""


class WebSecurity:
    @staticmethod
    def csrf_token() -> str:
        """Generated once per browser session, stored server-side — every
        form on every page renders the *same* token via `templates/base.html`'s
        shared macro.
        """
        token = session.get(CSRF_SESSION_KEY)
        if not token:
            token = secrets.token_urlsafe(32)
            session[CSRF_SESSION_KEY] = token
        return token

    @staticmethod
    def validate_csrf(request: Request) -> None:
        """Raises `CsrfValidationError` unless the submitted token exactly
        matches the session's own token. Called once, centrally, by
        `WebApplication`'s `before_request` hook for every state-changing
        (non-GET/HEAD/OPTIONS) request — no individual route has to remember
        to call this itself.
        """
        expected = session.get(CSRF_SESSION_KEY)
        submitted = request.form.get(CSRF_FORM_FIELD) or request.headers.get("X-CSRF-Token")
        if not expected or not submitted or not secrets.compare_digest(expected, submitted):
            raise CsrfValidationError("Missing or invalid CSRF token")

    @staticmethod
    def apply_security_headers(response: Response) -> Response:
        """"Suitable local-app security" (the mission's own words) — a
        single-user localhost app still deserves standard hardening headers;
        none of these depend on anything per-request.
        """
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'",
        )
        response.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        return response

    @staticmethod
    def safe_join(base_dir: Path, *parts: str) -> Path | None:
        """Resolves `base_dir / parts` and returns `None` if the result would
        escape `base_dir` — the exact defense
        `notifications/channels/file_channel.py::_resolve_path()` already
        established (see its own docstring), reused here rather than
        reinvented for serving report/image files from the web layer.
        """
        resolved_base = base_dir.resolve()
        try:
            candidate = resolved_base.joinpath(*parts).resolve()
        except (OSError, ValueError):
            return None
        if candidate != resolved_base and resolved_base not in candidate.parents:
            return None
        return candidate

    @staticmethod
    def is_safe_url(url: str) -> bool:
        """`http`/`https` only, with a real host — rejects `javascript:`,
        `file:`, `data:`, and any schemeless/host-less string a manual
        discovery-URL or webhook-configuration field might otherwise accept.
        """
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        return parsed.scheme in _ALLOWED_URL_SCHEMES and bool(parsed.netloc)
