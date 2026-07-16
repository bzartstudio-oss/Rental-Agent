"""`/api/v1/discovery-runs`, `/api/v1/platforms` — see
docs/32_Web_Dashboard.md "API Structure".
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.web.application import get_facade
from src.web.presenters.serialization import to_jsonable

blueprint = Blueprint("api_discovery", __name__)


@blueprint.route("/discovery-runs")
def list_runs():
    facade = get_facade()
    return jsonify(runs=[to_jsonable(r) for r in facade.discovery_history()])


@blueprint.route("/discovery-runs/candidates")
def list_candidates():
    facade = get_facade()
    return jsonify(candidates=[to_jsonable(c) for c in facade.list_candidates(status=request.args.get("status"))])


@blueprint.route("/platforms")
def list_platforms():
    facade = get_facade()
    connector_available_only = request.args.get("connector_available_only") == "1"
    return jsonify(platforms=[to_jsonable(p) for p in facade.list_platforms(connector_available_only=connector_available_only)])
