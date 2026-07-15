"""Unit tests for ProviderHealth / check_provider_health — src/providers/health.py."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import json

from src.discovery import platform_registry
from src.knowledge import knowledge_service
from src.providers.base import Provider, ProviderKind
from src.providers.health import check_provider_health
from src.providers.scoring import ProviderMetadata
from src.storage import search_repository
from src.storage.database import Database
from src.storage.models import Platform, SearchRequestRecord


class _FakeDataProvider(Provider):
    """A minimal stand-in with a `platform_id`, avoiding any dependency on
    `providers.data` (this module deliberately doesn't import `DataProvider` — see
    health.py's own docstring on why `getattr` is used instead of `isinstance`).
    """

    provider_id = "fake_data"
    kind = ProviderKind.DATA
    platform_id = "fake_platform"

    def __init__(self, available: bool = True) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider_id=self.provider_id, cost_score=0.0, freshness_score=1.0, quality_score=1.0)


class _FakeAIProvider(Provider):
    provider_id = "fake_ai"
    kind = ProviderKind.AI

    def is_available(self) -> bool:
        return True

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider_id=self.provider_id, cost_score=0.0, freshness_score=1.0, quality_score=1.0)


class ProviderHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_ai_provider_has_no_platform_id_or_connector_health(self) -> None:
        with self.db.transaction() as conn:
            health = check_provider_health(_FakeAIProvider(), conn)

        self.assertEqual(health.provider_id, "fake_ai")
        self.assertTrue(health.is_available_now)
        self.assertIsNone(health.platform_id)
        self.assertIsNone(health.connector_health)

    def test_data_provider_with_no_observations_yet_has_no_connector_health(self) -> None:
        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id="fake_platform", name="Fake", country="N/A", homepage="x",
                    connector_available=True, connector_name="fake", created_at=datetime.now(timezone.utc),
                ),
            )
            health = check_provider_health(_FakeDataProvider(), conn)

        self.assertEqual(health.platform_id, "fake_platform")
        self.assertIsNone(health.connector_health)  # honest "no evidence yet", not a fabricated zero

    def test_data_provider_with_real_observations_surfaces_connector_health(self) -> None:
        now = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id="fake_platform", name="Fake", country="N/A", homepage="x",
                    connector_available=True, connector_name="fake", created_at=now,
                ),
            )
            search_repository.insert_search_request(
                conn,
                SearchRequestRecord(id="search-1", created_at=now, criteria_json=json.dumps({"location": "x", "criteria": {}})),
            )
            knowledge_service.record_platform_observation(
                conn, "fake_platform", "search-1",
                results_count=5, failed=False, response_time_ms=120, raw_listings=None,
                ranking_usefulness_score=None, parsing_success=True, observed_at=now,
            )
            health = check_provider_health(_FakeDataProvider(), conn)

        self.assertIsNotNone(health.connector_health)
        self.assertEqual(health.connector_health.platform_id, "fake_platform")
        self.assertEqual(health.connector_health.success_count, 1)

    def test_is_available_now_reflects_the_providers_own_check(self) -> None:
        with self.db.transaction() as conn:
            health = check_provider_health(_FakeDataProvider(available=False), conn)

        self.assertFalse(health.is_available_now)


if __name__ == "__main__":
    unittest.main()
