"""Apartment Detail Page — see docs/32_Web_Dashboard.md "Apartment Detail
Page".
"""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from src.web.application import get_facade
from src.web.constants import DEFAULT_PROFILE_ID
from src.web.forms.validation import parse_safe_id
from src.web.presenters.apartment_presenter import present_missing_data_summary
from src.web.presenters.serialization import to_jsonable

blueprint = Blueprint("apartments", __name__, url_prefix="/apartments")


@blueprint.route("/<apartment_id>")
def detail(apartment_id: str):
    apartment_id = parse_safe_id(apartment_id, "Apartment id")
    facade = get_facade()
    search_id = request.args.get("search_id")
    data = facade.apartment_detail(apartment_id, search_id=search_id, profile_id=DEFAULT_PROFILE_ID)
    data["missing_data"] = present_missing_data_summary(data["apartment"])
    if request.accept_mimetypes.best == "application/json":
        return jsonify(to_jsonable(data))
    return render_template("apartments/detail.html", active_nav="search", **data)
