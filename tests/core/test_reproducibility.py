"""Phase 6 exit-criteria test (docs/10_Roadmap.md): running the same SearchRequest again
after the underlying fixture data changes must accumulate history, not overwrite it —
the first validation of Principles 1, 3, and 4 through the REAL orchestrator end-to-end
(Phase 1's test proved the schema supports this via direct repository calls; this proves
the whole pipeline actually behaves that way).

Simulates "re-scraping demo_platform later and finding a price change" by editing the
real fixture file in place between two runs, then restoring it in tearDown — the fixture
is shared with other tests, so mutating it without restoring would break them.
"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.core.agent import RentalResearchAgent
from src.discovery import platform_registry
from src.search.search_request import SearchRequest
from src.storage import apartment_repository, search_repository
from src.storage.database import Database
from src.storage.models import Platform
from tests.support import isolated_collectors

_FIXTURE_PATH = (
    Path(__file__).parents[2] / "src" / "connectors" / "fixtures" / "demo_platform" / "listings.html"
)


class ReRunAndCompareTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.output_dir = Path(self._tmp_dir.name) / "output"
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id="demo_platform",
                    name="Demo Platform (reference/demo connector, not real)",
                    base_url="local-fixture",
                    connector_module="src.connectors.demo_platform",
                    is_active=True,
                    created_at=datetime.now(timezone.utc),
                ),
            )

        self.agent = RentalResearchAgent(self.db, output_dir=self.output_dir)
        self._original_fixture_content = _FIXTURE_PATH.read_text(encoding="utf-8")

    def tearDown(self) -> None:
        _FIXTURE_PATH.write_text(self._original_fixture_content, encoding="utf-8")
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def _simulate_price_drop(self) -> None:
        """demo-001: 1450 -> 1350, as if the platform were re-scraped after a real change."""
        updated = self._original_fixture_content.replace(
            '<span class="price">1450</span>', '<span class="price">1350</span>'
        )
        _FIXTURE_PATH.write_text(updated, encoding="utf-8")

    def test_re_running_after_a_price_change_accumulates_history(self) -> None:
        first_result = self.agent.run(SearchRequest(location="Example City"))
        demo_001 = next(a for a in first_result.apartments if a.platform_listing_id == "demo-001")
        self.assertEqual(demo_001.current_price, 1450.0)

        self._simulate_price_drop()

        second_result = self.agent.run(SearchRequest(location="Example City"))
        updated_demo_001 = next(a for a in second_result.apartments if a.platform_listing_id == "demo-001")

        self.assertEqual(updated_demo_001.id, demo_001.id)  # same apartment, re-observed, not duplicated
        self.assertEqual(updated_demo_001.current_price, 1350.0)

        with self.db.transaction() as conn:
            price_history = apartment_repository.get_price_history(conn, demo_001.id)

        # Both observations survived, in order — nothing was lost or overwritten (Principles 1 & 3).
        self.assertEqual([entry.price for entry in price_history], [1450.0, 1350.0])

    def test_each_search_run_keeps_its_own_reproducible_snapshot(self) -> None:
        """Principle 4: each search's own results reflect the price *as observed at that
        search*, even after a later search changes the underlying apartment data — the
        first search's report doesn't silently change.
        """
        first_request = SearchRequest(location="Example City")
        first_result = self.agent.run(first_request)
        demo_001_id = next(a for a in first_result.apartments if a.platform_listing_id == "demo-001").id

        self._simulate_price_drop()

        second_request = SearchRequest(location="Example City")
        self.agent.run(second_request)

        with self.db.transaction() as conn:
            first_results = search_repository.get_search_results(conn, first_request.id)
            second_results = search_repository.get_search_results(conn, second_request.id)

        first_snapshot = next(r for r in first_results if r.apartment_id == demo_001_id)
        second_snapshot = next(r for r in second_results if r.apartment_id == demo_001_id)

        self.assertEqual(first_snapshot.price_at_search, 1450.0)
        self.assertEqual(second_snapshot.price_at_search, 1350.0)


if __name__ == "__main__":
    unittest.main()
