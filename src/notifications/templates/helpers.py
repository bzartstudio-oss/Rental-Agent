"""Small, shared read helpers every template uses to enrich an event with
apartment/report context — never a second report-generation implementation.
"Do not duplicate complete report generation logic" (the mission's own
words): templates only ever link to already-generated report files.
"""

from __future__ import annotations

import sqlite3

from src.monitoring import service as monitoring_service
from src.storage import apartment_repository
from src.storage.models import Apartment


def apartment_for_event(conn: sqlite3.Connection, apartment_id: str | None) -> Apartment | None:
    if not apartment_id:
        return None
    return apartment_repository.get_apartment(conn, apartment_id)


def apartment_image_paths(conn: sqlite3.Connection, apartment_id: str | None, *, include: bool) -> list[str]:
    if not include or not apartment_id:
        return []
    return [image.local_path for image in apartment_repository.get_images(conn, apartment_id)]


def report_links_for_run(conn: sqlite3.Connection, monitoring_run_id: str | None, *, include: bool) -> list[str]:
    if not include or not monitoring_run_id:
        return []
    artifacts = monitoring_service.get_report_artifacts_for_run(conn, monitoring_run_id)
    return [artifact.path for artifact in artifacts if artifact.report_type in ("full_html", "changes_html")]
