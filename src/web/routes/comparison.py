"""Comparison Page — see docs/32_Web_Dashboard.md "Comparison Page"."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from src.web.application import get_facade
from src.web.constants import DEFAULT_PROFILE_ID
from src.web.error_handler import WebValidationError
from src.web.forms.validation import parse_safe_id

blueprint = Blueprint("comparison", __name__, url_prefix="/compare")


@blueprint.route("", methods=["POST"])
def save():
    facade = get_facade()
    apartment_ids = [parse_safe_id(a, "Apartment id") for a in request.form.getlist("apartment_ids")]
    try:
        comparison_id = facade.save_comparison(apartment_ids, profile_id=DEFAULT_PROFILE_ID)
    except WebValidationError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("dashboard.index"))
    return redirect(url_for("comparison.view", comparison_id=comparison_id))


@blueprint.route("/<comparison_id>")
def view(comparison_id: str):
    facade = get_facade()
    record = facade.get_saved_comparison(comparison_id)
    apartments = facade.comparison_apartments(record.apartment_ids)
    return render_template("comparison/index.html", active_nav="search", apartments=apartments, comparison_id=comparison_id)
