"""Main Dashboard route — see docs/32_Web_Dashboard.md "Main Dashboard"."""

from __future__ import annotations

from flask import Blueprint, render_template

from src.web.application import get_facade
from src.web.constants import DEFAULT_PROFILE_ID

blueprint = Blueprint("dashboard", __name__)


@blueprint.route("/")
def index():
    facade = get_facade()
    snapshot = facade.dashboard_snapshot(DEFAULT_PROFILE_ID)
    return render_template("dashboard.html", active_nav="dashboard", **snapshot)
