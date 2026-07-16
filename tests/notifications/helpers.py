"""Shared fixture builders for the Notification Delivery Engine test suite
(not a test module itself — no `test_` prefix, so `unittest discover` skips
it). Mirrors `tests/support.py`'s own "not a test, just shared setup" role.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.discovery import platform_registry
from src.monitoring import MonitoringEngine
from src.monitoring import service as monitoring_service
from src.monitoring.models import MonitoringEvent, MonitoringRun, MonitoringRunStatus, SavedSearch
from src.storage.apartment_repository import insert_apartment
from src.storage.database import Database
from src.storage.models import Apartment, Platform

NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


def _ensure_demo_platform(conn, *, now: datetime = NOW) -> None:
    if platform_registry.get_platform(conn, "demo_platform") is None:
        platform_registry.register_platform(conn, Platform(
            id="demo_platform", name="Demo Platform", country="N/A (local fixture)", homepage="local-fixture",
            connector_available=True, connector_name="demo_platform", created_at=now,
        ))


def make_saved_search(db: Database, *, profile_id: str = "profile-1", name: str = "Example City Apartments", now: datetime = NOW) -> SavedSearch:
    engine = MonitoringEngine()
    return engine.create_saved_search(db, name, {"location": "Example City", "criteria": {}}, profile_id=profile_id, now=now)


def make_run(conn, saved_search: SavedSearch, *, now: datetime = NOW) -> MonitoringRun:
    run = MonitoringRun(
        saved_search_id=saved_search.saved_search_id, saved_search_version=saved_search.current_version,
        started_at=now, status=MonitoringRunStatus.COMPLETED, completed_at=now,
        platforms_attempted=["demo_platform"], platforms_succeeded=["demo_platform"], platforms_failed=[],
    )
    monitoring_service.record_run(conn, run)
    return run


def make_apartment(conn, *, apartment_id: str | None = None, price: float = 1200.0, status: str = "available", now: datetime = NOW) -> Apartment:
    _ensure_demo_platform(conn, now=now)
    apartment_id = apartment_id or str(uuid.uuid4())
    apartment = Apartment(
        id=apartment_id, platform_id="demo_platform", platform_listing_id=apartment_id,
        title="Cozy Example Apartment", url=f"https://example.com/listings/{apartment_id}",
        current_price=price, current_status=status, first_seen_at=now, last_seen_at=now,
    )
    insert_apartment(conn, apartment)
    return apartment


def make_event(
    conn, saved_search: SavedSearch, run: MonitoringRun, *, event_type: str = "new_match", severity: str = "info",
    significance: float = 0.6, apartment_id: str | None = None, now: datetime = NOW, acknowledged: bool = False,
    notification_eligible: bool = True, old_value: dict | None = None, new_value: dict | None = None,
) -> MonitoringEvent:
    event = MonitoringEvent(
        saved_search_id=saved_search.saved_search_id, saved_search_version=saved_search.current_version,
        monitoring_run_id=run.monitoring_run_id, event_type=event_type, severity=severity, significance=significance,
        explanation=f"{event_type} detected for a test apartment", evidence={"source": "test"}, detected_at=now,
        dedup_key=str(uuid.uuid4()), apartment_id=apartment_id, acknowledged=acknowledged,
        notification_eligible=notification_eligible, old_value=old_value, new_value=new_value,
    )
    monitoring_service.record_event(conn, event)
    return event
