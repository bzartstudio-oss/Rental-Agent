"""System Health UI — see docs/32_Web_Dashboard.md "System Health"."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from src.web.application import get_facade
from src.web.presenters.serialization import to_jsonable

blueprint = Blueprint("health", __name__, url_prefix="/health")


@blueprint.route("")
def index():
    facade = get_facade()
    health = facade.system_health()
    statistics = facade.system_statistics()
    active_jobs = facade.recent_jobs(limit=10)
    if request.accept_mimetypes.best == "application/json":
        return jsonify(health=to_jsonable(health), statistics=to_jsonable(statistics))
    return render_template("health/index.html", active_nav="health", health=health, statistics=statistics, active_jobs=active_jobs)
