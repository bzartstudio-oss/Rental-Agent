"""`/api/v1/health` — see docs/32_Web_Dashboard.md "API Structure"."""

from __future__ import annotations

from flask import Blueprint, jsonify

from src.web.application import get_facade
from src.web.presenters.serialization import to_jsonable

blueprint = Blueprint("api_health", __name__)


@blueprint.route("/health")
def health():
    facade = get_facade()
    return jsonify(health=to_jsonable(facade.system_health()), statistics=to_jsonable(facade.system_statistics()))
