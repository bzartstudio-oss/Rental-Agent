"""Monitoring UI — see docs/32_Web_Dashboard.md "Monitoring Workflow"."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from src.web.application import get_facade

blueprint = Blueprint("monitoring", __name__, url_prefix="/monitoring")


@blueprint.route("")
def index():
    facade = get_facade()
    saved_searches = facade.list_saved_searches()
    unacknowledged = facade.list_monitoring_events(unacknowledged_only=True)
    return render_template("monitoring/index.html", active_nav="monitoring", saved_searches=saved_searches, events=unacknowledged)


@blueprint.route("/saved-search/<saved_search_id>/events")
def events(saved_search_id: str):
    facade = get_facade()
    event_list = facade.list_monitoring_events(saved_search_id=saved_search_id)
    return render_template("monitoring/index.html", active_nav="monitoring", saved_searches=facade.list_saved_searches(),
                            events=event_list, filtered_saved_search_id=saved_search_id)


@blueprint.route("/events/<event_id>/acknowledge", methods=["POST"])
def acknowledge(event_id: str):
    get_facade().acknowledge_event(event_id, acknowledged_by="web_dashboard", note=request.form.get("note"))
    flash("Event acknowledged.", "success")
    return redirect(request.referrer or url_for("monitoring.index"))
