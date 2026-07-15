"""Tests for services/report_generator.py — new in v2.0 Step 6, since no dedicated
unit test file existed before (the generator was only ever exercised indirectly
through tests/core/test_agent.py's real-pipeline integration test). Covers the new
optional `analysis_results` parameter and confirms every existing caller's behavior
(no `analysis_results` passed) is unchanged.
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.analysis.models import AnalysisResult, AnalyzerResult, CompositeScore
from src.services.report_generator import generate_report
from src.storage import apartment_repository, search_repository
from src.storage.database import Database
from src.storage.models import Apartment, SearchRequestRecord, SearchResultEntry


class ReportGeneratorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.output_dir = Path(self._tmp_dir.name) / "output"
        now = datetime.now(timezone.utc)

        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO platforms (id, name, country, supported_cities, rental_types, homepage, "
                "connector_available, connector_name, discovery_method, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("test_platform", "Test", "Testland", "[]", "[]", "https://example.com", 1,
                 "src.connectors.test", "manual", now.isoformat()),
            )
            search_repository.insert_search_request(
                conn,
                SearchRequestRecord(
                    id="search-1", created_at=now,
                    criteria_json=json.dumps({"location": "Example City", "criteria": {}}),
                ),
            )
            apartment_repository.insert_apartment(
                conn,
                Apartment(
                    id="apt-1", platform_id="test_platform", platform_listing_id="listing-1",
                    title="A Nice Place", url="https://example.com/a", current_price=1000.0,
                    current_status="available", first_seen_at=now, last_seen_at=now,
                ),
            )
            search_repository.add_search_result(
                conn,
                SearchResultEntry(
                    search_id="search-1", apartment_id="apt-1", rank=1, score=0.9,
                    score_breakdown_json="{}", price_at_search=1000.0, status_at_search="available",
                ),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()


class BackwardCompatibilityTests(ReportGeneratorTestCase):
    def test_existing_callers_without_analysis_results_are_unaffected(self) -> None:
        report_path = generate_report(self.db, "search-1", output_dir=self.output_dir)

        content = report_path.read_text(encoding="utf-8")
        self.assertIn("A Nice Place", content)
        self.assertNotIn('class="analysis"', content)  # no section when nothing passed
        self.assertNotIn('class="ai-summary"', content)  # no section when nothing passed


class AnalysisSectionTests(ReportGeneratorTestCase):
    def _analysis_result(self) -> AnalysisResult:
        now = datetime.now(timezone.utc)
        return AnalysisResult(
            apartment_id="apt-1", search_id="search-1", computed_at=now,
            analyzer_results=[
                AnalyzerResult(
                    analyzer_name="walking_distance", apartment_id="apt-1", score=0.8, confidence=1.0,
                    evidence=["1.2 km from Example City center"], warnings=[], computed_at=now,
                    version="1.0.0", source="haversine_calculation",
                ),
                AnalyzerResult(
                    analyzer_name="nearby_supermarkets", apartment_id="apt-1", score=None, confidence=None,
                    evidence=[], warnings=["No curated supermarket data for 'Example City' yet"],
                    computed_at=now, version="1.0.0", source="knowledge_entries",
                ),
            ],
            composite_scores=[CompositeScore(name="location_score", score=0.8, component_analyzer_names=["walking_distance"])],
        )

    def test_analysis_section_shows_scores_evidence_and_composites(self) -> None:
        report_path = generate_report(
            self.db, "search-1", output_dir=self.output_dir,
            analysis_results={"apt-1": self._analysis_result()},
        )

        content = report_path.read_text(encoding="utf-8")
        self.assertIn('class="analysis"', content)
        self.assertIn("walking_distance", content)
        self.assertIn("0.80", content)
        self.assertIn("1.2 km from Example City center", content)
        self.assertIn("location_score", content)

    def test_analysis_section_shows_warnings_for_no_evidence_analyzers(self) -> None:
        report_path = generate_report(
            self.db, "search-1", output_dir=self.output_dir,
            analysis_results={"apt-1": self._analysis_result()},
        )

        content = report_path.read_text(encoding="utf-8")
        self.assertIn("nearby_supermarkets", content)
        self.assertIn("No curated supermarket data", content)
        self.assertIn("analysis-warning", content)

    def test_missing_analysis_for_an_apartment_omits_its_section_gracefully(self) -> None:
        report_path = generate_report(
            self.db, "search-1", output_dir=self.output_dir,
            analysis_results={},  # apt-1 has no entry
        )

        content = report_path.read_text(encoding="utf-8")
        self.assertIn("A Nice Place", content)
        self.assertNotIn('class="analysis"', content)


class EnrichedMetadataSectionTests(ReportGeneratorTestCase):
    """SDK Validation Sprint finding: Apartment already carries platform identity,
    currency, property type, coordinates, and a last-observed timestamp — this section
    proves the report actually surfaces them, closing that gap (see
    docs/22_SDK_Validation_Sprint.md "Question 4").
    """

    def test_platform_name_and_listing_id_are_shown(self) -> None:
        report_path = generate_report(self.db, "search-1", output_dir=self.output_dir)

        content = report_path.read_text(encoding="utf-8")
        self.assertIn("Platform: Test", content)  # platforms.name, not the raw id
        self.assertIn("Listing ID: listing-1", content)

    def test_missing_optional_fields_render_as_na_not_a_crash(self) -> None:
        report_path = generate_report(self.db, "search-1", output_dir=self.output_dir)

        content = report_path.read_text(encoding="utf-8")
        self.assertIn("Property type: n/a", content)
        self.assertIn("Currency: n/a", content)
        self.assertIn("Coordinates: n/a", content)

    def test_a_fully_populated_apartment_shows_every_enriched_field(self) -> None:
        now = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(
                conn,
                Apartment(
                    id="apt-2", platform_id="test_platform", platform_listing_id="listing-2",
                    title="A Richer Place", url="https://example.com/b", current_price=2000.0,
                    current_status="available", first_seen_at=now, last_seen_at=now,
                    latitude=40.7128, longitude=-74.0060, currency="USD", property_type="apartment",
                    description="A genuinely lovely apartment with a view.",
                ),
            )
            search_repository.add_search_result(
                conn,
                SearchResultEntry(
                    search_id="search-1", apartment_id="apt-2", rank=2, score=0.5,
                    score_breakdown_json="{}", price_at_search=2000.0, status_at_search="available",
                ),
            )

        content = generate_report(self.db, "search-1", output_dir=self.output_dir).read_text(encoding="utf-8")

        self.assertIn("Property type: apartment", content)
        self.assertIn("Currency: USD", content)
        self.assertIn("Coordinates: 40.71280, -74.00600", content)
        self.assertIn("Last updated:", content)
        self.assertIn("A genuinely lovely apartment with a view.", content)


class AISummarySectionTests(ReportGeneratorTestCase):
    def test_ai_summary_renders_when_provided(self) -> None:
        report_path = generate_report(
            self.db, "search-1", output_dir=self.output_dir,
            ai_summary="This search found one affordable, well-located apartment.",
        )

        content = report_path.read_text(encoding="utf-8")
        self.assertIn('class="ai-summary"', content)
        self.assertIn("This search found one affordable, well-located apartment.", content)

    def test_ai_summary_omitted_when_none(self) -> None:
        report_path = generate_report(self.db, "search-1", output_dir=self.output_dir, ai_summary=None)

        content = report_path.read_text(encoding="utf-8")
        self.assertNotIn('class="ai-summary"', content)

    def test_ai_summary_is_html_escaped(self) -> None:
        report_path = generate_report(
            self.db, "search-1", output_dir=self.output_dir,
            ai_summary="<script>alert('x')</script>",
        )

        content = report_path.read_text(encoding="utf-8")
        self.assertNotIn("<script>", content)
        self.assertIn("&lt;script&gt;", content)


if __name__ == "__main__":
    unittest.main()
