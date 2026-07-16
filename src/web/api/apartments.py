"""`/api/v1/apartments` — see docs/32_Web_Dashboard.md "API Structure"."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.web.application import get_facade
from src.web.constants import DEFAULT_PROFILE_ID
from src.web.forms.validation import parse_safe_id
from src.web.presenters.serialization import to_jsonable

blueprint = Blueprint("api_apartments", __name__)


@blueprint.route("/apartments/<apartment_id>")
def get_apartment(apartment_id: str):
    apartment_id = parse_safe_id(apartment_id, "Apartment id")
    facade = get_facade()
    data = facade.apartment_detail(apartment_id, search_id=request.args.get("search_id"), profile_id=DEFAULT_PROFILE_ID)
    return jsonify(to_jsonable(data))


@blueprint.route("/apartments/<apartment_id>/history")
def get_apartment_history(apartment_id: str):
    apartment_id = parse_safe_id(apartment_id, "Apartment id")
    facade = get_facade()
    data = facade.apartment_detail(apartment_id, profile_id=DEFAULT_PROFILE_ID)
    return jsonify(
        price_history=[to_jsonable(e) for e in data["price_history"]],
        availability_history=[to_jsonable(e) for e in data["availability_history"]],
        change_log=[to_jsonable(e) for e in data["change_log"]],
        image_events=[to_jsonable(e) for e in data["image_events"]],
    )
