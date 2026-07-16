"""Discovery UI — see docs/32_Web_Dashboard.md "Discovery Workflow"."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from src.web.application import get_facade
from src.web.constants import DEFAULT_PROFILE_ID
from src.web.error_handler import WebValidationError
from src.web.forms.discovery_form import parse_discovery_form

blueprint = Blueprint("discovery", __name__, url_prefix="/discovery")


@blueprint.route("")
def index():
    facade = get_facade()
    candidates = facade.list_candidates()
    platforms = facade.list_platforms()
    missing_connectors = facade.list_candidates(status="connector_missing")
    summary = facade.discovery_coverage_summary()
    return render_template("discovery/index.html", active_nav="discovery", candidates=candidates, platforms=platforms,
                            missing_connectors=missing_connectors, summary=summary)


@blueprint.route("/run", methods=["POST"])
def run():
    facade = get_facade()
    try:
        fields = parse_discovery_form(request.form)
        job = facade.start_discovery_run(profile_id=DEFAULT_PROFILE_ID, **fields)
    except WebValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("discovery.index"))
    flash(f"Discovery run started ({job.job_id[:8]}).", "success")
    return redirect(url_for("discovery.index"))


@blueprint.route("/candidates/<candidate_id>")
def candidate_detail(candidate_id: str):
    facade = get_facade()
    data = facade.get_candidate(candidate_id)
    return render_template("discovery/candidate.html", active_nav="discovery", **data)


@blueprint.route("/candidates/<candidate_id>/approve", methods=["POST"])
def approve(candidate_id: str):
    get_facade().approve_candidate(candidate_id, connector_name=request.form.get("connector_name") or None)
    flash("Candidate approved into the Platform Registry.", "success")
    return redirect(url_for("discovery.candidate_detail", candidate_id=candidate_id))


@blueprint.route("/candidates/<candidate_id>/reject", methods=["POST"])
def reject(candidate_id: str):
    get_facade().reject_candidate(candidate_id, reason=request.form.get("reason") or None)
    flash("Candidate rejected.", "success")
    return redirect(url_for("discovery.candidate_detail", candidate_id=candidate_id))
