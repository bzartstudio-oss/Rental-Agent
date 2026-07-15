"""Unit tests for ProviderMetrics — src/providers/metrics.py. Verifies the dataclass
is built from the exact same `src.knowledge.metrics` formulas already used elsewhere
(not a second, independently-derived computation), and that recording it writes a
real `platform_performance_observations` row via the existing Knowledge Engine path.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.connectors.base import RawListing
from src.connectors.sdk.result import ConnectorResult
from src.discovery import platform_registry
from src.knowledge import knowledge_service
from src.providers.metrics import build_provider_metrics, record_provider_metrics
from src.storage import search_repository
from src.storage.database import Database
from src.storage.models import Platform, SearchRequestRecord


def _listing(listing_id: str, has_image: bool = True, status: str | None = "available") -> RawListing:
    return RawListing(
        platform_listing_id=listing_id,
        title="A Place",
        price=1000.0,
        url="https://example.com/x",
        bedrooms=1,
        bathrooms=1,
        sqft=500,
        address_raw="123 Main St",
        status=status,
        image_urls=["https://example.com/img.jpg"] if has_image else [],
    )


class BuildProviderMetricsTests(unittest.TestCase):
    def test_successful_result_with_full_field_coverage(self) -> None:
        result = ConnectorResult(
            platform_id="rentcast", listings=[_listing("a"), _listing("b")], success=True,
            started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
            response_time_ms=250,
        )

        metrics = build_provider_metrics("rentcast", "rentcast", result)

        self.assertEqual(metrics.provider_id, "rentcast")
        self.assertEqual(metrics.platform_id, "rentcast")
        self.assertEqual(metrics.execution_time_ms, 250)
        self.assertTrue(metrics.success)
        self.assertEqual(metrics.listing_count, 2)
        self.assertEqual(metrics.duplicate_rate, 0.0)
        self.assertEqual(metrics.extraction_quality_score, 1.0)
        self.assertEqual(metrics.image_quality_score, 1.0)
        self.assertEqual(metrics.availability_quality_score, 1.0)

    def test_duplicate_listings_are_reflected_in_duplicate_rate(self) -> None:
        result = ConnectorResult(
            platform_id="rentcast", listings=[_listing("a"), _listing("a")], success=True,
            started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
        )

        metrics = build_provider_metrics("rentcast", "rentcast", result)
        self.assertEqual(metrics.duplicate_rate, 0.5)

    def test_missing_images_and_status_lower_the_quality_scores(self) -> None:
        result = ConnectorResult(
            platform_id="rentcast", listings=[_listing("a", has_image=False, status=None)], success=True,
            started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
        )

        metrics = build_provider_metrics("rentcast", "rentcast", result)
        self.assertEqual(metrics.image_quality_score, 0.0)
        self.assertEqual(metrics.availability_quality_score, 0.0)

    def test_empty_results_never_crash_and_produce_none_quality_scores(self) -> None:
        result = ConnectorResult(
            platform_id="rentcast", listings=[], success=True,
            started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
        )

        metrics = build_provider_metrics("rentcast", "rentcast", result)
        self.assertEqual(metrics.listing_count, 0)
        self.assertIsNone(metrics.duplicate_rate)
        self.assertIsNone(metrics.extraction_quality_score)

    def test_failed_result_carries_the_error_through(self) -> None:
        result = ConnectorResult(
            platform_id="rentcast", listings=[], success=False, error="boom",
            started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
        )

        metrics = build_provider_metrics("rentcast", "rentcast", result)
        self.assertFalse(metrics.success)
        self.assertEqual(metrics.error, "boom")


class RecordProviderMetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_writes_a_real_observation_via_the_knowledge_engine(self) -> None:
        now = datetime.now(timezone.utc)
        result = ConnectorResult(
            platform_id="rentcast", listings=[_listing("a")], success=True,
            started_at=now, finished_at=now, response_time_ms=99,
        )
        metrics = build_provider_metrics("rentcast", "rentcast", result)

        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id="rentcast", name="RentCast", country="US", homepage="x",
                    connector_available=True, connector_name="rentcast", created_at=now,
                ),
            )
            search_repository.insert_search_request(
                conn,
                SearchRequestRecord(id="search-1", created_at=now, criteria_json=json.dumps({"location": "x", "criteria": {}})),
            )
            record_provider_metrics(conn, metrics, result, "search-1", now)
            health = knowledge_service.connector_health(conn, platform_id="rentcast")

        self.assertEqual(len(health), 1)
        self.assertEqual(health[0].success_count, 1)
        self.assertEqual(health[0].avg_response_time_ms, 99)


if __name__ == "__main__":
    unittest.main()
