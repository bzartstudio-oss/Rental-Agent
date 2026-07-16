"""`/api/v1/monitoring-events` — see docs/32_Web_Dashboard.md "API Structure"."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.web.application import get_facade
from src.web.presenters.serialization import to_jsonable

blueprint = Blueprint("api_monitoring", __name__)


@blueprint.route("/monitoring-events")
def list_events():
    facade = get_facade()
    saved_search_id = request.args.get("saved_search_id")
    unacknowledged_only = request.args.get("unacknowledged_only") == "1"
    events = facade.list_monitoring_events(saved_search_id=saved_search_id, unacknowledged_only=unacknowledged_only)
    return jsonify(events=[to_jsonable(e) for e in events])


@blueprint.route("/monitoring-events/<event_id>/acknowledge", methods=["POST"])
def acknowledge_event(event_id: str):
    facade = get_facade()
    facade.acknowledge_event(event_id, acknowledged_by="api")
    return jsonify(status="acknowledged")
