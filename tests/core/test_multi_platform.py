"""Phase 7 exit-criteria test (docs/10_Roadmap.md): a second connector
(demo_platform_two, a differently-shaped fixture) plugs into the real orchestrator
alongside the first, producing results from both — with zero changes to analyzers/,
ranking/, storage/, or services/ needed to add it (proven simply by the fact this test
doesn't touch any of those files). If it hadn't worked without changes elsewhere, that
would be a sign the Principle 7 independence boundary had leaked somewhere in Phases 1-5.
"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.core.agent import RentalResearchAgent
from src.discovery import platform_registry
from src.search.search_request import SearchRequest
from src.storage.database import Database
from src.storage.models import Platform
from tests.support import isolated_collectors


class MultiPlatformTests(unittest.TestCase):
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
            platform_registry.register_platform(
                conn,
                Platform(
                    id="demo_platform_two",
                    name="Demo Platform Two (reference/demo connector, not real)",
                    base_url="local-fixture",
                    connector_module="src.connectors.demo_platform_two",
                    is_active=True,
                    created_at=datetime.now(timezone.utc),
                ),
            )

        self.agent = RentalResearchAgent(self.db, output_dir=self.output_dir)

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def test_both_platforms_contribute_results_to_one_search(self) -> None:
        result = self.agent.run(SearchRequest(location="Example City"))

        self.assertEqual(len(result.apartments), 6)  # 3 from each platform

        by_platform = {}
        for apartment in result.apartments:
            by_platform.setdefault(apartment.platform_id, []).append(apartment)

        self.assertEqual(len(by_platform["demo_platform"]), 3)
        self.assertEqual(len(by_platform["demo_platform_two"]), 3)

    def test_report_includes_listings_from_both_platforms(self) -> None:
        result = self.agent.run(SearchRequest(location="Example City"))

        content = result.report_path.read_text(encoding="utf-8")

        self.assertIn("Bright 2BR Near the Park", content)  # from demo_platform
        self.assertIn("Modern 1BR Loft", content)  # from demo_platform_two


if __name__ == "__main__":
    unittest.main()
