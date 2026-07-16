"""HTML routes — see docs/32_Web_Dashboard.md "Route Structure".

Every blueprint module here calls `get_facade()` and nothing else for data —
no SQL, no direct engine construction, no business calculation. `register_routes()`
is the one place every blueprint is wired into the app.
"""

from __future__ import annotations

from flask import Flask


def register_routes(app: Flask) -> None:
    from src.web.routes import (
        apartments,
        comparison,
        dashboard,
        discovery,
        feedback,
        health,
        monitoring,
        notifications,
        saved_searches,
        search,
    )

    app.register_blueprint(dashboard.blueprint)
    app.register_blueprint(search.blueprint)
    app.register_blueprint(apartments.blueprint)
    app.register_blueprint(comparison.blueprint)
    app.register_blueprint(saved_searches.blueprint)
    app.register_blueprint(monitoring.blueprint)
    app.register_blueprint(notifications.blueprint)
    app.register_blueprint(discovery.blueprint)
    app.register_blueprint(feedback.blueprint)
    app.register_blueprint(health.blueprint)
