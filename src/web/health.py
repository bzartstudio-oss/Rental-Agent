"""`WebHealth` — aggregates every existing engine's own health signal into one
read for the System Health page. See docs/32_Web_Dashboard.md "System Health".

Every underlying number comes from an existing engine's own health function
(`knowledge_service.connector_health`, `providers.health.check_provider_health`,
`notifications.service.compute_channel_health`,
`monitoring.scheduling.compute_health`) — this module only collects and shapes
them for display, never recomputes a health verdict itself.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from src.discovery import platform_registry
from src.knowledge import knowledge_service
from src.monitoring import scheduling as monitoring_scheduling
from src.monitoring import service as monitoring_service
from src.notifications.registry import NotificationChannelRegistry
from src.notifications import service as notification_service
from src.providers.health import check_provider_health
from src.providers.registry import ProviderRegistry
from src.storage.database import Database


@dataclass
class WebHealth:
    database_ok: bool
    migration_count: int
    connector_health: list = field(default_factory=list)
    provider_health: list = field(default_factory=list)
    notification_channel_health: list = field(default_factory=list)
    monitoring_health: list = field(default_factory=list)
    recent_failures: list[str] = field(default_factory=list)

    @classmethod
    def collect(cls, db: Database, conn: sqlite3.Connection) -> "WebHealth":
        database_ok, migration_count = _database_status(conn)

        connector_health = knowledge_service.connector_health(conn)
        provider_health = [check_provider_health(provider, conn) for provider in ProviderRegistry.all()]
        notification_channel_health = [
            notification_service.compute_channel_health(conn, channel.channel_name)
            for channel in NotificationChannelRegistry.all()
        ]
        monitoring_health = [
            monitoring_scheduling.compute_health(conn, saved_search.saved_search_id)
            for saved_search in monitoring_service.get_all_saved_searches(conn)
        ]

        recent_failures: list[str] = []
        for health in connector_health:
            if health.failure_count > 0:
                recent_failures.append(f"Connector {health.platform_id!r}: {health.failure_count} failed observation(s)")
        for health in monitoring_health:
            if health.consecutive_failure_count > 0:
                recent_failures.append(f"Saved search {health.saved_search_id!r}: {health.consecutive_failure_count} consecutive failed run(s)")
        for health in notification_channel_health:
            if not health.is_healthy:
                recent_failures.append(f"Notification channel {health.channel!r} is unhealthy")

        return cls(
            database_ok=database_ok, migration_count=migration_count, connector_health=connector_health,
            provider_health=provider_health, notification_channel_health=notification_channel_health,
            monitoring_health=monitoring_health, recent_failures=recent_failures,
        )


def _database_status(conn: sqlite3.Connection) -> tuple[bool, int]:
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM schema_migrations").fetchone()["c"]
        return True, count
    except sqlite3.Error:
        return False, 0
