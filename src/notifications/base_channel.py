"""`NotificationChannel` — the plugin contract every delivery channel
implements. Mirrors `src.connectors.sdk.base_connector.BaseConnector`'s own
"one shared template, small platform-specific hooks" shape, adapted to the
mission's own named interface: `configure()`/`validate_configuration()`/
`supports()`/`health_check()`/`preview()`/`send()`/`send_batch()`/
`serialize_result()`/`channel_info()`.

"Email and webhook channels must be configurable and disabled by default
unless valid configuration is supplied" (the mission's own words):
`is_enabled()` — not a stored flag — is always exactly
`validate_configuration()`'s live answer, so a channel can never claim to be
enabled while genuinely misconfigured.
"""

from __future__ import annotations

import sqlite3
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from src.notifications.metadata import NotificationChannelMetadata
from src.notifications.models import NotificationChannelResult, NotificationHealth, NotificationMessage


class NotificationChannel(ABC):
    channel_name: str

    def __init__(self, config: dict | None = None) -> None:
        self.configure(config or {})

    def configure(self, config: dict) -> None:
        """Stores `config` verbatim as `self._config` — override to also parse/
        validate specific keys (e.g. `EmailNotificationChannel` reading
        `smtp_host`/`smtp_port`).
        """
        self._config = dict(config)

    def is_enabled(self) -> bool:
        return self.validate_configuration()

    def send_batch(self, messages: list[NotificationMessage]) -> list[NotificationChannelResult]:
        """Default: one `send()` call per message, independently — a single
        message's failure doesn't affect the others. Override only for a
        channel with a genuine bulk API.
        """
        return [self.send(message) for message in messages]

    def serialize_result(self, result: NotificationChannelResult) -> dict:
        """JSON-safe shape for storage/logging — "Redact secrets from logs and
        exceptions" (the mission's own words) applies here: subclasses that
        include channel-specific detail in `result.metadata` must keep secrets
        out of it in the first place; this base implementation never echoes
        `self._config` back.
        """
        return {
            "channel": result.channel, "success": result.success, "error": result.error,
            "error_category": result.error_category, "duration_ms": result.duration_ms,
            "external_id": result.external_id, "metadata": result.metadata,
        }

    def health_check(self, conn: sqlite3.Connection) -> NotificationHealth:
        """Reused, not reimplemented per channel — every channel's send
        history already lives in `channel_health_observations` via the engine
        recording one row per attempt; see `service.compute_channel_health()`.
        """
        from src.notifications import service

        return service.compute_channel_health(conn, self.channel_name)

    def _timed_result(self, channel: str, started_at: float, *, success: bool, error: str | None = None,
                       error_category: str | None = None, external_id: str | None = None, metadata: dict | None = None) -> NotificationChannelResult:
        return NotificationChannelResult(
            channel=channel, success=success, error=error, error_category=error_category,
            duration_ms=int((time.monotonic() - started_at) * 1000), external_id=external_id, metadata=metadata or {},
        )

    # ------------------------------------------------------------------ #
    # Genuinely channel-specific — every channel must implement these.
    # ------------------------------------------------------------------ #

    @abstractmethod
    def validate_configuration(self) -> bool:
        """Whether this channel instance currently has everything it needs to
        actually send — never a stored flag, always a live check.
        """
        raise NotImplementedError

    @abstractmethod
    def supports(self, capability: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def preview(self, message: NotificationMessage) -> str:
        """A human-readable rendering of what `send(message)` would do —
        "Support preview mode without sending" (the mission's own words) —
        never performs the actual network/file/print side effect.
        """
        raise NotImplementedError

    @abstractmethod
    def send(self, message: NotificationMessage) -> NotificationChannelResult:
        """Never raises for an ordinary delivery failure (a closed SMTP
        connection, a 500 from a webhook endpoint) — those are honest
        `success=False` results, not exceptions; only a genuine programming
        bug should propagate.
        """
        raise NotImplementedError

    @abstractmethod
    def channel_info(self) -> NotificationChannelMetadata:
        raise NotImplementedError
