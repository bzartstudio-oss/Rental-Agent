"""JSON API v1 — see docs/32_Web_Dashboard.md "API Structure".

Every endpoint here calls the exact same `WebServiceFacade` the HTML routes
use — no business logic lives in this package, only request parsing and
`to_jsonable()` serialization. Mounted under `/api/v1/`, exempt from CSRF
(see `application.py`'s `before_request` hook) since it's not a browser-form
target, but still same-origin-only by default (localhost binding).
"""

from __future__ import annotations

from flask import Flask

from src.web.constants import API_PREFIX


def register_api(app: Flask) -> None:
    from src.web.api import (
        apartments,
        discovery,
        feedback,
        health,
        monitoring,
        notifications,
        preferences,
        saved_searches,
        searches,
    )

    app.register_blueprint(searches.blueprint, url_prefix=API_PREFIX)
    app.register_blueprint(apartments.blueprint, url_prefix=API_PREFIX)
    app.register_blueprint(saved_searches.blueprint, url_prefix=API_PREFIX)
    app.register_blueprint(monitoring.blueprint, url_prefix=API_PREFIX)
    app.register_blueprint(notifications.blueprint, url_prefix=API_PREFIX)
    app.register_blueprint(feedback.blueprint, url_prefix=API_PREFIX)
    app.register_blueprint(preferences.blueprint, url_prefix=API_PREFIX)
    app.register_blueprint(discovery.blueprint, url_prefix=API_PREFIX)
    app.register_blueprint(health.blueprint, url_prefix=API_PREFIX)
