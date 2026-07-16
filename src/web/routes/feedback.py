"""Feedback UI — see docs/32_Web_Dashboard.md "Feedback Workflow"."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from src.feedback.models import FeedbackMode
from src.web.application import get_facade
from src.web.constants import DEFAULT_PROFILE_ID
from src.web.error_handler import WebValidationError
from src.web.forms.feedback_form import parse_feedback_form

blueprint = Blueprint("feedback", __name__, url_prefix="/preferences")


@blueprint.route("")
def index():
    facade = get_facade()
    mode = FeedbackMode(request.args.get("mode", FeedbackMode.SUGGESTED.value))
    profile = facade.preference_profile(DEFAULT_PROFILE_ID, mode=mode)
    return render_template("feedback/index.html", active_nav="feedback", profile=profile, mode=mode.value)


@blueprint.route("/record", methods=["POST"])
def record():
    facade = get_facade()
    try:
        fields = parse_feedback_form(request.form)
        facade.record_feedback_event(profile_id=DEFAULT_PROFILE_ID, **fields)
    except WebValidationError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("feedback.index"))
    flash("Feedback recorded.", "success")
    return redirect(request.referrer or url_for("feedback.index"))


@blueprint.route("/<preference_key>/explain")
def explain(preference_key: str):
    facade = get_facade()
    evidence = facade.explain_preference(DEFAULT_PROFILE_ID, preference_key)
    history = facade.preference_history(DEFAULT_PROFILE_ID, preference_key)
    return render_template("feedback/explain.html", active_nav="feedback", preference_key=preference_key, evidence=evidence, history=history)


@blueprint.route("/<preference_key>/undo/<int:adjustment_id>", methods=["POST"])
def undo(preference_key: str, adjustment_id: int):
    get_facade().undo_preference_adjustment(DEFAULT_PROFILE_ID, preference_key, adjustment_id)
    flash("Adjustment undone.", "success")
    return redirect(url_for("feedback.explain", preference_key=preference_key))


@blueprint.route("/reset", methods=["POST"])
def reset():
    get_facade().reset_inferred_preferences(DEFAULT_PROFILE_ID)
    flash("Inferred preferences reset.", "success")
    return redirect(url_for("feedback.index"))
