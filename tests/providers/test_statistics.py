"""Unit tests for ProviderStatistics / provider_statistics — src/providers/statistics.py."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.discovery import platform_registry
from src.knowledge import knowledge_service
from src.providers.base import Provider, ProviderKind
from src.providers.scoring import ProviderMetadata
from src.providers.statistics import provider_statistics
from src.storage import search_repository
from src.storage.database import Database
from src.storage.models import Platform, SearchRequestRecord


class _FakeDataProvider(Provider):
    provider_id = "fake_data"
    kind = ProviderKind.DATA
    platform_id = "fake_platform"

    def is_available(self) -> bool:
        return True

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider_id=self.provider_id, cost_score=0.0, freshness_score=1.0, quality_score=1.0)


class _FakeAIProvider(Provider):
    provider_id = "fake_ai"
    kind = ProviderKind.AI

    def is_available(self) -> bool:
        return True

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider_id=self.provider_id, cost_score=0.0, freshness_score=1.0, quality_score=1.0)


class ProviderStatisticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_ai_provider_has_no_platform_knowledge(self) -> None:
        with self.db.transaction() as conn:
            stats = provider_statistics(_FakeAIProvider(), conn)

        self.assertIsNone(stats.platform_id)
        self.assertIsNone(stats.platform_knowledge)

    def test_data_provider_with_unregistered_platform_degrades_gracefully(self) -> None:
        with self.db.transaction() as conn:
            stats = provider_statistics(_FakeDataProvider(), conn)  # platforms table has no "fake_platform" row

        self.assertEqual(stats.platform_id, "fake_platform")
        self.assertIsNone(stats.platform_knowledge)

    def test_data_provider_with_real_observations_returns_platform_knowledge(self) -> None:
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
                results_count=3, failed=False, response_time_ms=100, raw_listings=None,
                ranking_usefulness_score=None, parsing_success=True, observed_at=now,
            )
            stats = provider_statistics(_FakeDataProvider(), conn)

        self.assertIsNotNone(stats.platform_knowledge)
        self.assertEqual(stats.platform_knowledge.platform_id, "fake_platform")
        self.assertEqual(stats.platform_knowledge.observation_count, 1)


if __name__ == "__main__":
    unittest.main()
