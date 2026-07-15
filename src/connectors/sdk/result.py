"""The uniform return shape of `BaseConnector.search()` — see
docs/18_Connector_SDK.md "Lifecycle".

Every connector, regardless of source (HTML/Playwright, HTTP/JSON, a future GraphQL or
RSS source), returns one of these. `core/agent.py` never inspects a connector's
internals — it reads `.success`/`.listings`/`.error`/`.response_time_ms` uniformly.
This is also what replaced the ad hoc per-platform metrics dict `core/agent.py` used to
build by hand in v2.0 Step 4 — the timing/count/failure data the Knowledge Engine needs
now comes from the connector itself, measured once, not re-derived by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.connectors.base import RawListing
from src.connectors.sdk.validator import ValidationWarning


@dataclass
class ConnectorResult:
    platform_id: str
    listings: list[RawListing]
    success: bool
    started_at: datetime
    finished_at: datetime
    response_time_ms: int | None = None
    error: str | None = None
    validation_warnings: list[ValidationWarning] = field(default_factory=list)

    @property
    def results_count(self) -> int:
        return len(self.listings)
