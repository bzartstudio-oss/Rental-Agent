"""`/api/v1/searches`, `/api/v1/search-jobs` — see
docs/32_Web_Dashboard.md "API Structure".
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.web.application import get_facade
from src.web.constants import DEFAULT_PROFILE_ID
from src.web.forms.search_form import parse_search_form
from src.web.presenters.serialization import to_jsonable

blueprint = Blueprint("api_searches", __name__)


@blueprint.route("/search-jobs", methods=["POST"])
def create_job():
    """Accepts the same `application/x-www-form-urlencoded` body the HTML
    search form posts — see `web.forms.search_form.parse_search_form()`,
    which needs `.getlist()` for multi-value fields (a plain JSON body can't
    represent that the same way, so this endpoint is form-encoded-only).
    """
    facade = get_facade()
    fields = parse_search_form(request.form)
    job = facade.start_search(
        profile_id=DEFAULT_PROFILE_ID, location=fields["location"], criteria=fields["criteria"], label=fields["label"],
        use_filter_engine=fields["use_filter_engine"], use_geo_engine=fields["use_geo_engine"],
        ranking_weights=fields["ranking_weights"], feedback_mode=fields["feedback_mode"],
        allowed_platform_ids=fields["allowed_platform_ids"],
    )
    return jsonify(job=to_jsonable(job)), 202


@blueprint.route("/search-jobs/<job_id>")
def get_job(job_id: str):
    facade = get_facade()
    return jsonify(job=to_jsonable(facade.get_job(job_id)))


@blueprint.route("/search-jobs")
def list_jobs():
    facade = get_facade()
    return jsonify(jobs=[to_jsonable(job) for job in facade.recent_jobs(limit=50)])


@blueprint.route("/searches/<search_id>")
def get_search(search_id: str):
    facade = get_facade()
    data = facade.search_results(search_id)
    return jsonify(
        request=to_jsonable(data["request"]),
        entries=[to_jsonable(entry) for entry in data["entries"]],
        apartments={aid: to_jsonable(a) for aid, a in data["apartments"].items()},
        ranking_v2=data["ranking_v2"],
    )
