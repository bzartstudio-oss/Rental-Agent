"""RentCast — the first production (non-demo) Connector SDK connector, added in v2.0
Step 7. See docs/20_First_Production_Connector.md for the full write-up: why this
source was chosen, the verified schema, supported fields, and known limitations.

Importing this package (as `ConnectorRegistry._ensure_imported("rentcast")` does,
following the `src.connectors.<connector_name>` convention) is what runs
`RentCastConnector`'s `@register_connector` decorator — the same self-registration
every other connector uses.
"""

from __future__ import annotations

from src.connectors.rentcast.connector import RentCastConnector

__all__ = ["RentCastConnector"]
