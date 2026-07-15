"""Unit tests for ProviderValidator — src/providers/validator.py. Confirms it
validates provider-level concerns (declared metadata ranges, surfaced connector
result warnings) without re-deriving listing-level validation
(`ConnectorValidator`'s job, already run inside `BaseConnector.search()`).
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.connectors.sdk.result import ConnectorResult
from src.connectors.sdk.validator import ValidationWarning
from src.providers.base import Provider, ProviderKind
from src.providers.exceptions import ProviderValidationError
from src.providers.scoring import ProviderMetadata
from src.providers.validator import ProviderValidator


class _ScriptedProvider(Provider):
    provider_id = "scripted"
    kind = ProviderKind.DATA

    def __init__(self, cost_score=0.5, freshness_score=0.5, quality_score=0.5):
        self._metadata = ProviderMetadata(
            provider_id=self.provider_id, cost_score=cost_score, freshness_score=freshness_score, quality_score=quality_score
        )

    def is_available(self) -> bool:
        return True

    def metadata(self) -> ProviderMetadata:
        return self._metadata


class MetadataValidationTests(unittest.TestCase):
    def test_metadata_within_range_produces_no_warnings(self) -> None:
        result = ProviderValidator.validate(_ScriptedProvider())
        self.assertTrue(result.is_valid)
        self.assertEqual(result.warnings, [])

    def test_a_score_above_one_produces_a_warning(self) -> None:
        result = ProviderValidator.validate(_ScriptedProvider(quality_score=1.5))
        self.assertFalse(result.is_valid)
        self.assertIn("quality_score", result.warnings[0])

    def test_a_negative_score_produces_a_warning(self) -> None:
        result = ProviderValidator.validate(_ScriptedProvider(cost_score=-0.1))
        self.assertFalse(result.is_valid)
        self.assertIn("cost_score", result.warnings[0])

    def test_strict_mode_raises_instead_of_returning_invalid(self) -> None:
        with self.assertRaises(ProviderValidationError):
            ProviderValidator.validate(_ScriptedProvider(freshness_score=2.0), strict=True)

    def test_strict_mode_does_not_raise_when_valid(self) -> None:
        result = ProviderValidator.validate(_ScriptedProvider(), strict=True)  # must not raise
        self.assertTrue(result.is_valid)


class ResultValidationTests(unittest.TestCase):
    def _result(self, warnings: list[ValidationWarning]) -> ConnectorResult:
        now = datetime.now(timezone.utc)
        return ConnectorResult(
            platform_id="x", listings=[], success=True, started_at=now, finished_at=now,
            validation_warnings=warnings,
        )

    def test_no_connector_warnings_means_valid(self) -> None:
        result = ProviderValidator.validate(_ScriptedProvider(), self._result([]))
        self.assertTrue(result.is_valid)

    def test_connector_warnings_are_surfaced_not_recomputed(self) -> None:
        warning = ValidationWarning(field="title", message="'title' is missing or empty")
        result = ProviderValidator.validate(_ScriptedProvider(), self._result([warning]))

        self.assertFalse(result.is_valid)
        self.assertIn("title", result.warnings[0])
        self.assertIn("missing or empty", result.warnings[0])

    def test_omitting_result_validates_metadata_only(self) -> None:
        result = ProviderValidator.validate(_ScriptedProvider())  # no ConnectorResult — fine for an AIProvider
        self.assertTrue(result.is_valid)


if __name__ == "__main__":
    unittest.main()
