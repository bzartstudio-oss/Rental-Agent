"""Tests for src/analysis/analyzers/nearby_amenity.py — the shared base class and all
nine "nearby X" analyzer subclasses.
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.analysis.analyzers.nearby_amenity import (
    NearbyGymsAnalyzer,
    NearbyHospitalsAnalyzer,
    NearbyParkingAnalyzer,
    NearbyParksAnalyzer,
    NearbyPharmaciesAnalyzer,
    NearbyRestaurantsAnalyzer,
    NearbySchoolsAnalyzer,
    NearbySupermarketsAnalyzer,
    NearbyUniversitiesAnalyzer,
)
from src.analysis.models import AnalysisContext
from src.storage import reference_data_repository
from src.storage.database import Database
from src.storage.models import Apartment, KnowledgeEntry

_ALL_NEARBY_ANALYZERS = [
    (NearbySupermarketsAnalyzer, "nearby_supermarkets", "supermarket"),
    (NearbyPharmaciesAnalyzer, "nearby_pharmacies", "pharmacy"),
    (NearbyHospitalsAnalyzer, "nearby_hospitals", "hospital"),
    (NearbyUniversitiesAnalyzer, "nearby_universities", "university"),
    (NearbySchoolsAnalyzer, "nearby_schools", "school"),
    (NearbyParksAnalyzer, "nearby_parks", "park"),
    (NearbyRestaurantsAnalyzer, "nearby_restaurants", "restaurant"),
    (NearbyGymsAnalyzer, "nearby_gyms", "gym"),
    (NearbyParkingAnalyzer, "nearby_parking", "parking"),
]


def _make_apartment() -> Apartment:
    now = datetime.now(timezone.utc)
    return Apartment(
        id="apt-1", platform_id="test_platform", platform_listing_id="listing-1", title="A",
        url="https://example.com/a", current_price=1000.0, current_status="available",
        first_seen_at=now, last_seen_at=now,
    )


class NearbyAmenityAnalyzersTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.apartment = _make_apartment()

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _context(self, conn) -> AnalysisContext:
        return AnalysisContext(conn=conn, location="Example City", computed_at=datetime.now(timezone.utc))

    def test_every_nearby_analyzer_has_correct_identity_and_metadata(self) -> None:
        for analyzer_class, expected_name, expected_amenity_type in _ALL_NEARBY_ANALYZERS:
            with self.subTest(analyzer=expected_name):
                analyzer = analyzer_class()
                self.assertEqual(analyzer.analyzer_name, expected_name)
                self.assertEqual(analyzer.amenity_type, expected_amenity_type)
                metadata = analyzer.metadata()
                self.assertEqual(metadata.analyzer_name, expected_name)
                self.assertEqual(metadata.category, "amenity")

    def test_every_nearby_analyzer_reports_no_evidence_without_curated_data(self) -> None:
        with self.db.transaction() as conn:
            context = self._context(conn)
            for analyzer_class, expected_name, _ in _ALL_NEARBY_ANALYZERS:
                with self.subTest(analyzer=expected_name):
                    result = analyzer_class().analyze(self.apartment, context)
                    self.assertIsNone(result.score)
                    self.assertIsNone(result.confidence)
                    self.assertTrue(result.warnings)

    def test_every_nearby_analyzer_computes_a_real_score_with_curated_data(self) -> None:
        with self.db.transaction() as conn:
            for _, _, amenity_type in _ALL_NEARBY_ANALYZERS:
                reference_data_repository.upsert_knowledge_entry(
                    conn,
                    KnowledgeEntry(
                        category="nearby_amenities", key=f"Example City:{amenity_type}",
                        value_json=json.dumps({"count": 3}), updated_at=datetime.now(timezone.utc),
                    ),
                )

            context = self._context(conn)
            for analyzer_class, expected_name, _ in _ALL_NEARBY_ANALYZERS:
                with self.subTest(analyzer=expected_name):
                    result = analyzer_class().analyze(self.apartment, context)
                    self.assertEqual(result.score, 0.6)  # 3 / saturation of 5
                    self.assertEqual(result.confidence, 0.8)
                    self.assertEqual(result.warnings, [])
                    self.assertEqual(len(result.evidence), 1)

    def test_score_saturates_at_the_configured_count(self) -> None:
        with self.db.transaction() as conn:
            reference_data_repository.upsert_knowledge_entry(
                conn,
                KnowledgeEntry(
                    category="nearby_amenities", key="Example City:supermarket",
                    value_json=json.dumps({"count": 50}), updated_at=datetime.now(timezone.utc),
                ),
            )
            result = NearbySupermarketsAnalyzer().analyze(self.apartment, self._context(conn))

        self.assertEqual(result.score, 1.0)  # never exceeds 1.0 no matter how large the count


if __name__ == "__main__":
    unittest.main()
