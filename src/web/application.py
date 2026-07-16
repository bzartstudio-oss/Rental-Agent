"""`WebApplication` — the Flask app factory. See docs/32_Web_Dashboard.md
"Startup Instructions"/"Architecture".

`create_app()` is the one function every entry point (the dev server, the
test suite, a future WSGI deployment) calls — it never does anything a route
could instead, keeping this file thin the same way `ui/cli.py` stays thin
over `core/agent.py`.
"""

from __future__ import annotations

from flask import Flask, g, request

from src.storage.database import Database
from src.web.configuration import WebConfiguration
from src.web.dependencies import WebDependencies
from src.web.error_handler import WebErrorHandler
from src.web.facade import WebServiceFacade
from src.web.security import CsrfValidationError, WebSecurity

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def create_app(*, db: Database | None = None, configuration: WebConfiguration | None = None) -> Flask:
    """`db`/`configuration` are optional so tests can point the app at a
    temporary database/config instead of the real project one — the same
    pattern every existing CLI's own `main(argv, db=None)` already uses.
    """
    configuration = configuration or WebConfiguration.from_env()
    db = db if db is not None else Database()
    dependencies = WebDependencies(db=db, configuration=configuration)
    facade = WebServiceFacade(dependencies)

    app = Flask(__name__, template_folder="templates", static_folder="static", static_url_path="/static")
    app.config["SECRET_KEY"] = configuration.secret_key
    app.config["MAX_CONTENT_LENGTH"] = configuration.max_content_length
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    app.extensions["web_dependencies"] = dependencies
    app.extensions["web_facade"] = facade

    WebErrorHandler.register(app)

    @app.before_request
    def _enforce_csrf() -> None:
        if request.method not in _SAFE_METHODS and not request.path.startswith("/api/"):
            WebSecurity.validate_csrf(request)

    @app.after_request
    def _add_security_headers(response):
        return WebSecurity.apply_security_headers(response)

    from src.web.presenters.status_presenter import (
        delivery_status_css_class,
        health_badge,
        job_status_css_class,
        severity_css_class,
    )

    # Registered as real Jinja *globals* (env.globals), not via
    # `@app.context_processor` — a `{% from "_macros.html" import ... %}`
    # import doesn't see the calling template's context (only `with context`
    # would, and only `_macros.html`'s own callers would need to remember
    # that), but every template already sees `env.globals` automatically.
    app.jinja_env.globals["csrf_token"] = WebSecurity.csrf_token
    app.jinja_env.globals["severity_css_class"] = severity_css_class
    app.jinja_env.globals["job_status_css_class"] = job_status_css_class
    app.jinja_env.globals["delivery_status_css_class"] = delivery_status_css_class
    app.jinja_env.globals["health_badge"] = health_badge

    from src.web.api import register_api
    from src.web.routes import register_routes

    register_routes(app)
    register_api(app)

    return app


def get_facade() -> WebServiceFacade:
    from flask import current_app

    return current_app.extensions["web_facade"]


def get_dependencies() -> WebDependencies:
    from flask import current_app

    return current_app.extensions["web_dependencies"]
