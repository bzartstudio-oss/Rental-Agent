"""`/api/v1/saved-searches`, `/api/v1/monitoring-runs` — see
docs/32_Web_Dashboard.md "API Structure".
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.web.application import get_facade
from src.web.presenters.serialization import to_jsonable

blueprint = Blueprint("api_saved_searches", __name__)


@blueprint.route("/saved-searches")
def list_saved_searches():
    facade = get_facade()
    enabled_only = request.args.get("enabled_only") == "1"
    return jsonify(saved_searches=[to_jsonable(s) for s in facade.list_saved_searches(enabled_only=enabled_only)])


@blueprint.route("/saved-searches/<saved_search_id>")
def get_saved_search(saved_search_id: str):
    facade = get_facade()
    data = facade.get_saved_search(saved_search_id)
    return jsonify(to_jsonable(data))
