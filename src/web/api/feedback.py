"""`/api/v1/feedback` — see docs/32_Web_Dashboard.md "API Structure"."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.web.application import get_facade
from src.web.constants import DEFAULT_PROFILE_ID
from src.web.error_handler import WebValidationError
from src.web.forms.feedback_form import parse_feedback_form
from src.web.presenters.serialization import to_jsonable

blueprint = Blueprint("api_feedback", __name__)


@blueprint.route("/feedback", methods=["POST"])
def record_feedback():
    facade = get_facade()
    fields = parse_feedback_form(request.form)
    event = facade.record_feedback_event(profile_id=DEFAULT_PROFILE_ID, **fields)
    return jsonify(event=to_jsonable(event)), 201


@blueprint.route("/feedback/history")
def feedback_history():
    facade = get_facade()
    return jsonify(events=[to_jsonable(e) for e in facade.export_feedback_history(DEFAULT_PROFILE_ID)])
