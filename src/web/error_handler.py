"""`WebErrorHandler` — centralized error handling. See
docs/32_Web_Dashboard.md "Security Model": "no raw tracebacks shown to users."

Every handler distinguishes an HTML request (renders a template) from a JSON
API request (`/api/v1/...` or an `Accept: application/json` request) so the
mission's "user-friendly errors for HTML and structured errors for JSON"
requirement holds without any route needing its own try/except.
"""

from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from src.utils.logging import get_logger
from src.web.security import CsrfValidationError

logger = get_logger(__name__)


class WebValidationError(Exception):
    """Raised by forms/routes for a malformed or rejected user input —
    the one exception type every route can raise to get a consistent
    400 response, HTML or JSON.
    """


class WebNotFoundError(Exception):
    """Raised when a route's own lookup (a job/apartment/saved-search/etc.
    id) resolves to nothing — a consistent 404, HTML or JSON.
    """


def _wants_json() -> bool:
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"


class WebErrorHandler:
    @staticmethod
    def register(app: Flask) -> None:
        app.register_error_handler(WebValidationError, WebErrorHandler._handle_validation_error)
        app.register_error_handler(WebNotFoundError, WebErrorHandler._handle_not_found_error)
        app.register_error_handler(CsrfValidationError, WebErrorHandler._handle_csrf_error)
        app.register_error_handler(404, WebErrorHandler._handle_404)
        app.register_error_handler(400, WebErrorHandler._handle_400)
        app.register_error_handler(500, WebErrorHandler._handle_500)
        app.register_error_handler(413, WebErrorHandler._handle_413)

    @staticmethod
    def _handle_validation_error(exc: WebValidationError):
        if _wants_json():
            return jsonify(error="validation_error", message=str(exc)), 400
        return render_template("errors/400.html", message=str(exc)), 400

    @staticmethod
    def _handle_not_found_error(exc: WebNotFoundError):
        if _wants_json():
            return jsonify(error="not_found", message=str(exc)), 404
        return render_template("errors/404.html", message=str(exc)), 404

    @staticmethod
    def _handle_csrf_error(exc: CsrfValidationError):
        if _wants_json():
            return jsonify(error="csrf_validation_failed", message=str(exc)), 400
        return render_template("errors/400.html", message="Your session expired or the form was resubmitted. Please try again."), 400

    @staticmethod
    def _handle_404(exc):
        if _wants_json():
            return jsonify(error="not_found", message="The requested resource was not found."), 404
        return render_template("errors/404.html", message="Page not found."), 404

    @staticmethod
    def _handle_400(exc):
        if _wants_json():
            return jsonify(error="bad_request", message="The request could not be understood."), 400
        return render_template("errors/400.html", message="The request could not be understood."), 400

    @staticmethod
    def _handle_413(exc):
        if _wants_json():
            return jsonify(error="payload_too_large", message="The request body is too large."), 413
        return render_template("errors/400.html", message="The submitted data is too large."), 413

    @staticmethod
    def _handle_500(exc):
        # "no raw tracebacks shown to users" (the mission's own words) — the
        # real exception is logged server-side only, never rendered.
        logger.error("Unhandled web application error", extra={"path": request.path}, exc_info=exc)
        if _wants_json():
            return jsonify(error="internal_error", message="An unexpected error occurred."), 500
        return render_template("errors/500.html", message="An unexpected error occurred."), 500
