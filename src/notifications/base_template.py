"""`NotificationTemplate` — the plugin contract every message template
implements, and `TemplateContext`/`RenderedTemplate` — the shared input/output
shapes. "Do not hardcode channel-specific message construction throughout the
engine" (the mission's own words): every template renders one channel-neutral
`RenderedTemplate` (plain text + optional HTML); a channel picks whichever
body it supports.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from src.monitoring.models import MonitoringEvent
from src.notifications.models import NotificationPreferenceVersion


@dataclass
class TemplateContext:
    conn: sqlite3.Connection
    events: list[MonitoringEvent]
    preference_version: NotificationPreferenceVersion
    now: datetime
    saved_search_name: str | None = None
    frequency: str | None = None  # set for digest templates: "hourly"/"daily"/"weekly"/"manual"
    period_start: datetime | None = None
    period_end: datetime | None = None


@dataclass
class RenderedTemplate:
    subject: str
    body_text: str
    body_html: str | None = None
    original_listing_urls: list[str] = field(default_factory=list)
    report_links: list[str] = field(default_factory=list)


class NotificationTemplate(ABC):
    template_name: str
    version: int = 1
    event_types: tuple[str, ...] = ()  # empty = digest/catch-all template, not event-type-matched
    channel_compatibility: tuple[str, ...] = ()  # empty = every channel

    @abstractmethod
    def render(self, context: TemplateContext) -> RenderedTemplate:
        raise NotImplementedError
