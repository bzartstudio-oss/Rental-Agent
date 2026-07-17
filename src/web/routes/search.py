"""New Search Workflow + job execution + results — see
docs/32_Web_Dashboard.md "Search Workflow".
"""

from __future__ import annotations

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from src.web.application import get_facade
from src.web.constants import DEFAULT_PROFILE_ID
from src.web.error_handler import WebValidationError
from src.web.forms.config_loader import parse_config_file
from src.web.forms.search_form import parse_search_form
from src.web.presenters.apartment_presenter import present_apartment_card, present_missing_data_summary
from src.web.presenters.serialization import to_jsonable

blueprint = Blueprint("search", __name__, url_prefix="/search")


@blueprint.route("/new", methods=["GET"])
def new_search():
    facade = get_facade()
    filters = facade.available_filters()
    categories: dict[str, list] = {}
    for metadata in filters:
        categories.setdefault(metadata.category, []).append(metadata)
    platforms = facade.list_platforms(connector_available_only=True)
    return render_template("search/new.html", active_nav="search", filter_categories=categories, platforms=platforms)


@blueprint.route("/new", methods=["POST"])
def submit_search():
    """v2.6 Milestone 2.6.3 — an uploaded `config_file` (matching
    `config/pilot.example.json`'s shape) is an *additional*, optional way to
    reach the exact same `fields` this route has always built from
    `request.form` — every other field on the New Search form is still read
    and validated exactly as before when no file is uploaded. See
    src/web/forms/config_loader.py.
    """
    facade = get_facade()
    config_file = request.files.get("config_file")
    try:
        if config_file is not None and config_file.filename:
            fields = parse_config_file(config_file.read())
        else:
            fields = parse_search_form(request.form)
    except WebValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("search.new_search"))

    if fields["save_search"] and fields["saved_search_name"]:
        facade.create_saved_search(
            name=fields["saved_search_name"], location=fields["location"], criteria=fields["criteria"],
            profile_id=DEFAULT_PROFILE_ID, enable_monitoring=fields["enable_monitoring"],
        )

    job = facade.start_search(
        profile_id=DEFAULT_PROFILE_ID, location=fields["location"], criteria=fields["criteria"], label=fields["label"],
        use_filter_engine=fields["use_filter_engine"], use_geo_engine=fields["use_geo_engine"],
        ranking_weights=fields["ranking_weights"], feedback_mode=fields["feedback_mode"],
        allowed_platform_ids=fields["allowed_platform_ids"],
    )
    return redirect(url_for("search.job_status", job_id=job.job_id))


@blueprint.route("/jobs/<job_id>")
def job_status(job_id: str):
    facade = get_facade()
    job = facade.get_job(job_id)
    if request.accept_mimetypes.best == "application/json":
        return jsonify(job=to_jsonable(job))
    return render_template("search/job.html", active_nav="search", job=job)


@blueprint.route("/jobs/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id: str):
    facade = get_facade()
    facade.request_job_cancellation(job_id)
    flash("Cancellation requested.", "success")
    return redirect(url_for("search.job_status", job_id=job_id))


@blueprint.route("/results/<search_id>")
def results(search_id: str):
    facade = get_facade()
    data = facade.search_results(search_id)
    cards = []
    for entry in data["entries"]:
        apartment = data["apartments"].get(entry.apartment_id)
        if apartment is None:
            continue
        ranking_v2 = data["ranking_v2"].get(entry.apartment_id)
        card = present_apartment_card(apartment, ranking_v2=ranking_v2)
        card["missing_data"] = present_missing_data_summary(apartment)
        cards.append(card)
    return render_template("search/results.html", active_nav="search", request_record=data["request"], cards=cards, search_id=search_id)
