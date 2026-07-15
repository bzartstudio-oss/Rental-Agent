"""Per-connector runtime configuration — see docs/18_Connector_SDK.md.

Separate from `ConnectorMetadata` (what a connector *is*, fixed per class) — this is
how a connector is *run*, overridable per instantiation without touching the
connector's own code. `ConnectorFactory.get()` accepts one; `BaseConnector.__init__`
defaults to `ConnectorConfiguration()` when none is given, so existing call sites
(`ConnectorFactory.get(platform)`) don't need to change to pick up the defaults.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConnectorConfiguration:
    headless: bool = True
    timeout_ms: int = 30_000
    max_retries: int = 0
    rate_limit_per_minute: int | None = None
    credentials: dict[str, str] | None = None
    # Off by default: no existing connector's listings have ever needed outright
    # rejection — see ConnectorValidationError. A future strict caller can opt in.
    strict_validation: bool = False
