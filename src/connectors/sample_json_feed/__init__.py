"""SampleJsonFeedConnector — a third reference connector built for the SDK Validation
Sprint. See docs/22_SDK_Validation_Sprint.md and connector.py's own docstring.

Importing this package (as `ConnectorRegistry._ensure_imported("sample_json_feed")`
would, following the `src.connectors.<connector_name>` convention) is what runs
`SampleJsonFeedConnector`'s `@register_connector` decorator.
"""

from __future__ import annotations

from src.connectors.sample_json_feed.connector import SampleJsonFeedConnector

__all__ = ["SampleJsonFeedConnector"]
