"""`/api/v1/preferences` — the *learned preference profile*, distinct from
`/api/v1/notifications/preferences` (notification delivery settings). See
docs/32_Web_Dashboard.md "API Structure".
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.feedback.models import FeedbackMode
from src.web.application import get_facade
from src.web.constants import DEFAULT_PROFILE_ID
from src.web.presenters.serialization import to_jsonable

blueprint = Blueprint("api_preferences", __name__)


@blueprint.route("/preferences")
def get_preference_profile():
    facade = get_facade()
    mode = FeedbackMode(request.args.get("mode", FeedbackMode.SUGGESTED.value))
    profile = facade.preference_profile(DEFAULT_PROFILE_ID, mode=mode)
    return jsonify(to_jsonable(profile))
