"""Notifications UI — see docs/32_Web_Dashboard.md "Notification Workflow"."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from src.web.application import get_facade
from src.web.constants import DEFAULT_PROFILE_ID
from src.web.error_handler import WebValidationError
from src.web.forms.notification_form import parse_notification_preference_form

blueprint = Blueprint("notifications", __name__, url_prefix="/notifications")


@blueprint.route("")
def index():
    facade = get_facade()
    preferences = facade.list_notification_preferences(profile_id=DEFAULT_PROFILE_ID)
    channels = facade.channel_config_status()
    pending = facade.list_deliveries(status="pending")
    failed = facade.list_deliveries(status="failed")
    delivered = facade.list_deliveries(profile_id=DEFAULT_PROFILE_ID)
    return render_template("notifications/index.html", active_nav="notifications", preferences=preferences,
                            channels=channels, pending=pending, failed=failed, delivered=delivered[:20])


@blueprint.route("/preferences/new", methods=["GET"])
def new_preference():
    facade = get_facade()
    channels = facade.channel_config_status()
    saved_search_id = request.args.get("saved_search_id")
    return render_template("notifications/form.html", active_nav="notifications", channels=channels, saved_search_id=saved_search_id)


@blueprint.route("/preferences/new", methods=["POST"])
def create_preference():
    facade = get_facade()
    try:
        fields = parse_notification_preference_form(request.form)
        facade.create_notification_preference(profile_id=DEFAULT_PROFILE_ID, **fields)
    except WebValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("notifications.new_preference"))
    flash("Notification preference created.", "success")
    return redirect(url_for("notifications.index"))


@blueprint.route("/preferences/<preference_id>/enable", methods=["POST"])
def enable(preference_id: str):
    get_facade().set_notification_enabled(preference_id, True)
    flash("Notifications enabled.", "success")
    return redirect(url_for("notifications.index"))


@blueprint.route("/preferences/<preference_id>/disable", methods=["POST"])
def disable(preference_id: str):
    get_facade().set_notification_enabled(preference_id, False)
    flash("Notifications disabled.", "success")
    return redirect(url_for("notifications.index"))


@blueprint.route("/preferences/<preference_id>/preview", methods=["GET"])
def preview_form(preference_id: str):
    facade = get_facade()
    events = facade.list_monitoring_events(unacknowledged_only=True)
    return render_template("notifications/preview.html", active_nav="notifications", preference_id=preference_id,
                            events=events, rendered=None)


@blueprint.route("/preferences/<preference_id>/preview", methods=["POST"])
def preview_submit(preference_id: str):
    facade = get_facade()
    event_ids = request.form.getlist("event_ids")
    channel_name = request.form.get("channel_name", "console")
    try:
        rendered = facade.preview_notification(preference_id, event_ids, channel_name)
    except WebValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("notifications.preview_form", preference_id=preference_id))
    events = facade.list_monitoring_events(unacknowledged_only=True)
    return render_template("notifications/preview.html", active_nav="notifications", preference_id=preference_id,
                            events=events, rendered=rendered)


@blueprint.route("/deliveries/<delivery_id>")
def delivery_detail(delivery_id: str):
    facade = get_facade()
    data = facade.get_delivery(delivery_id)
    return render_template("notifications/delivery.html", active_nav="notifications", **data)


@blueprint.route("/deliveries/<delivery_id>/acknowledge", methods=["POST"])
def acknowledge_delivery(delivery_id: str):
    get_facade().acknowledge_delivery(delivery_id, acknowledged_by="web_dashboard")
    flash("Delivery acknowledged.", "success")
    return redirect(url_for("notifications.delivery_detail", delivery_id=delivery_id))


@blueprint.route("/deliveries/<delivery_id>/retry", methods=["POST"])
def retry_delivery(delivery_id: str):
    get_facade().retry_delivery(delivery_id)
    flash("Retry attempted.", "success")
    return redirect(url_for("notifications.delivery_detail", delivery_id=delivery_id))


@blueprint.route("/deliveries/<delivery_id>/cancel", methods=["POST"])
def cancel_delivery(delivery_id: str):
    get_facade().cancel_delivery(delivery_id)
    flash("Delivery cancelled.", "success")
    return redirect(url_for("notifications.delivery_detail", delivery_id=delivery_id))


@blueprint.route("/deliver-pending", methods=["POST"])
def deliver_pending():
    batch = get_facade().deliver_pending_notifications()
    flash(f"Processed {batch.deliveries_attempted} delivery attempt(s).", "success")
    return redirect(url_for("notifications.index"))
