"""`/api/v1/notifications` — see docs/32_Web_Dashboard.md "API Structure"."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.web.application import get_facade
from src.web.constants import DEFAULT_PROFILE_ID
from src.web.presenters.serialization import to_jsonable

blueprint = Blueprint("api_notifications", __name__)


@blueprint.route("/notifications/preferences")
def list_preferences():
    facade = get_facade()
    return jsonify(preferences=[to_jsonable(p) for p in facade.list_notification_preferences(profile_id=DEFAULT_PROFILE_ID)])


@blueprint.route("/notifications/deliveries")
def list_deliveries():
    facade = get_facade()
    status = request.args.get("status")
    deliveries = facade.list_deliveries(profile_id=DEFAULT_PROFILE_ID, status=status)
    return jsonify(deliveries=[to_jsonable(d) for d in deliveries])


@blueprint.route("/notifications/deliveries/<delivery_id>")
def get_delivery(delivery_id: str):
    facade = get_facade()
    return jsonify(to_jsonable(facade.get_delivery(delivery_id)))


@blueprint.route("/notifications/channels")
def channel_status():
    facade = get_facade()
    return jsonify(channels=[to_jsonable(c) for c in facade.channel_config_status()])
