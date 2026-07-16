"""Saved Searches workflow — see docs/32_Web_Dashboard.md "Saved-Search
Workflow".
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from src.web.application import get_facade
from src.web.constants import DEFAULT_PROFILE_ID
from src.web.error_handler import WebValidationError
from src.web.forms.saved_search_form import parse_saved_search_form
from src.web.forms.search_form import parse_search_form

blueprint = Blueprint("saved_searches", __name__, url_prefix="/saved-searches")


@blueprint.route("")
def index():
    facade = get_facade()
    saved_searches = facade.list_saved_searches()
    return render_template("saved_searches/list.html", active_nav="saved_searches", saved_searches=saved_searches)


@blueprint.route("/new", methods=["GET"])
def new():
    facade = get_facade()
    filters = facade.available_filters()
    categories: dict[str, list] = {}
    for metadata in filters:
        categories.setdefault(metadata.category, []).append(metadata)
    return render_template("saved_searches/form.html", active_nav="saved_searches", filter_categories=categories)


@blueprint.route("/new", methods=["POST"])
def create():
    facade = get_facade()
    try:
        fields = parse_saved_search_form(request.form)
        facade.create_saved_search(
            name=fields["name"], location=fields["location"], criteria=fields["criteria"],
            profile_id=DEFAULT_PROFILE_ID, description=fields["description"],
            enable_monitoring=fields["enable_monitoring"], geographic_destinations=fields["geographic_destinations"],
        )
    except WebValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("saved_searches.new"))
    flash("Saved search created.", "success")
    return redirect(url_for("saved_searches.index"))


@blueprint.route("/<saved_search_id>")
def detail(saved_search_id: str):
    facade = get_facade()
    data = facade.get_saved_search(saved_search_id)
    return render_template("saved_searches/detail.html", active_nav="saved_searches", **data)


@blueprint.route("/<saved_search_id>/enable", methods=["POST"])
def enable(saved_search_id: str):
    get_facade().set_monitoring_enabled(saved_search_id, True)
    flash("Monitoring enabled.", "success")
    return redirect(url_for("saved_searches.detail", saved_search_id=saved_search_id))


@blueprint.route("/<saved_search_id>/disable", methods=["POST"])
def disable(saved_search_id: str):
    get_facade().set_monitoring_enabled(saved_search_id, False)
    flash("Monitoring disabled.", "success")
    return redirect(url_for("saved_searches.detail", saved_search_id=saved_search_id))


@blueprint.route("/<saved_search_id>/run-now", methods=["POST"])
def run_now(saved_search_id: str):
    facade = get_facade()
    job = facade.run_saved_search_now(saved_search_id, profile_id=DEFAULT_PROFILE_ID)
    return redirect(url_for("search.job_status", job_id=job.job_id))


@blueprint.route("/<saved_search_id>/compare-runs")
def compare_runs(saved_search_id: str):
    facade = get_facade()
    run_a, run_b = request.args.get("run_a"), request.args.get("run_b")
    comparison = None
    if run_a and run_b:
        comparison = facade.compare_monitoring_runs(run_a, run_b)
    data = facade.get_saved_search(saved_search_id)
    return render_template("saved_searches/detail.html", active_nav="saved_searches", comparison=comparison, **data)
