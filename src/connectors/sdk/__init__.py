"""The Connector SDK & Plugin Framework (v2.0 Step 5) — see docs/18_Connector_SDK.md.

The framework every future connector builds on, so that adding a new rental platform
requires creating one connector module implementing four small hooks
(`build_url`/`parse`/`normalize`/`connector_info`) and inheriting everything else —
fetching, raw-page persistence, validation, health reporting, capability discovery,
structured errors, and registration — from `BaseConnector`.

Public API, re-exported here so callers don't need to know this package's internal
file layout:
"""

from __future__ import annotations

from src.connectors.sdk.base_connector import BaseConnector
from src.connectors.sdk.configuration import ConnectorConfiguration
from src.connectors.sdk.exceptions import (
    ConnectorConfigurationError,
    ConnectorConnectionError,
    ConnectorException,
    ConnectorParsingError,
    ConnectorValidationError,
)
from src.connectors.sdk.factory import ConnectorFactory
from src.connectors.sdk.metadata import ConnectorCapabilities, ConnectorMetadata
from src.connectors.sdk.registry import ConnectorRegistry, register_connector
from src.connectors.sdk.result import ConnectorResult
from src.connectors.sdk.validator import ConnectorValidator, ValidationResult, ValidationWarning

# ConnectorHealth is NOT redefined here — it's src.knowledge.models.ConnectorHealth
# (v2.0 Step 4), re-exported so "ConnectorHealth" is discoverable from this package
# without a caller needing to know it actually lives in knowledge/. See
# BaseConnector.health_check() and docs/18_Connector_SDK.md "Connector Health" for why
# this SDK deliberately doesn't define a second, competing ConnectorHealth class.
from src.knowledge.models import ConnectorHealth

__all__ = [
    "BaseConnector",
    "ConnectorCapabilities",
    "ConnectorConfiguration",
    "ConnectorConfigurationError",
    "ConnectorConnectionError",
    "ConnectorException",
    "ConnectorFactory",
    "ConnectorHealth",
    "ConnectorMetadata",
    "ConnectorParsingError",
    "ConnectorRegistry",
    "ConnectorResult",
    "ConnectorValidationError",
    "ConnectorValidator",
    "ValidationResult",
    "ValidationWarning",
    "register_connector",
]
