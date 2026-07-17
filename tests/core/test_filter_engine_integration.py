"""Agent-level integration tests for the Dynamic Filter Engine — proving
`RentalResearchAgent`'s optional `filter_engine` parameter actually changes pipeline
behavior end-to-end (real Playwright fetch of the real local demo fixture), and that
the default (no filter_engine) path is completely unaffected — see
tests/core/test_agent.py, still passing unmodified.
"""

from __future__ import annotations

import contextlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse
from urllib.request import url2pathname

from src.core.agent import RentalResearchAgent
from src.discovery import platform_registry
from src.filter_engine import FilterEngine
from src.search.search_request import SearchRequest
from src.storage import reference_data_repository
from src.storage.database import Database
from src.storage.models import KnowledgeEntry, Platform
from tests.support import isolated_collectors


class _FileReadingBrowser:
    """Stands in for a real `BrowserCollector` — `DemoPlatformConnector.build_url()`
    always returns a `file://` URI, so "fetching" it is just reading the file,
    avoiding the real-Chromium-launch flakiness `tests/core/test_provider_integration.py`
    already found and worked around this session.
    """

    def fetch(self, url: str, wait_ms: int = 0) -> str:
        return Path(url2pathname(urlparse(url).path)).read_text(encoding="utf-8")


@contextlib.contextmanager
def _mock_browser_collector():
    with patch("src.connectors.sdk.base_connector.BrowserCollector") as mock_cls:
        mock_cls.return_value.__enter__.return_value = _FileReadingBrowser()
        yield


class FilterEngineIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.output_dir = Path(self._tmp_dir.name) / "output"
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()
        self._browser_cm = _mock_browser_collector()
        self._browser_cm.__enter__()

        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id="demo_platform", name="Demo Platform", country="N/A", homepage="local-fixture",
                    connector_available=True, connector_name="demo_platform",
                    created_at=datetime.now(timezone.utc),
                ),
            )

    def tearDown(self) -> None:
        self._browser_cm.__exit__(None, None, None)
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def test_default_behavior_unchanged_when_no_filter_engine_given(self) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir)  # no filter_engine
        result = agent.run(SearchRequest(location="Example City"))
        self.assertEqual(len(result.apartments), 3)  # the demo fixture's 3 listings, all pass

    def test_filter_engine_narrows_results_through_the_real_pipeline(self) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, filter_engine=FilterEngine())
        result = agent.run(SearchRequest(location="Example City", criteria={"max_price": 1000}))

        # The fixture's real prices are 1450/950/2100 (src/connectors/fixtures/
        # demo_platform/listings.html) — max_price=1000 keeps only the 950 listing.
        self.assertEqual(len(result.apartments), 1)
        self.assertLessEqual(result.apartments[0].current_price, 1000)

    def test_filter_history_is_recorded(self) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, filter_engine=FilterEngine())
        result = agent.run(SearchRequest(location="Example City", criteria={"max_price": 1000}))

        from src.filter_engine import get_filter_history

        with self.db.transaction() as conn:
            history = get_filter_history(conn, result.search_id)

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].filter_set, {"max_price": 1000})
        self.assertGreaterEqual(history[0].total_apartments, history[0].matched_count)

    def test_dormant_filter_criteria_does_not_exclude_real_apartments(self) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, filter_engine=FilterEngine())
        result = agent.run(SearchRequest(location="Example City", criteria={"private_bathroom": True}))

        self.assertEqual(len(result.apartments), 3)  # dormant filter never excludes

    def test_currency_filter_now_discriminates_against_enriched_demo_data(self) -> None:
        """v2.6 Milestone 2.6.2 (docs/41_Version_2.6_Planning.md) — before this, every
        demo apartment's `currency` was `None`, so `CurrencyFilter` (fail-closed on
        unknown currency) excluded every result no matter what currency was
        requested. The fixture's listings are now all `EUR` (see
        src/connectors/fixtures/demo_platform/listings.html): requesting "EUR" must
        match all 3, requesting a different real currency must match none.
        """
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, filter_engine=FilterEngine())

        matching = agent.run(SearchRequest(location="Example City", criteria={"currency": "EUR"}))
        self.assertEqual(len(matching.apartments), 3)

        non_matching = agent.run(SearchRequest(location="Example City", criteria={"currency": "USD"}))
        self.assertEqual(len(non_matching.apartments), 0)

    def test_property_type_filter_now_discriminates_against_enriched_demo_data(self) -> None:
        """Same rationale as the currency test above — the fixture's 3 listings are
        now 2 "apartment" and 1 "studio" (see the same fixture file), so
        `PropertyTypeFilter` can now tell them apart instead of excluding everything.
        """
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, filter_engine=FilterEngine())

        apartments_only = agent.run(SearchRequest(location="Example City", criteria={"property_type": "apartment"}))
        self.assertEqual(len(apartments_only.apartments), 2)

        studios_only = agent.run(SearchRequest(location="Example City", criteria={"property_type": "studio"}))
        self.assertEqual(len(studios_only.apartments), 1)
        self.assertEqual(studios_only.apartments[0].property_type, "studio")

    def test_walking_distance_filter_discriminates_once_a_curated_reference_point_exists(self) -> None:
        """Real coordinates alone (v2.6 Milestone 2.6.2) are not sufficient for
        `WalkingDistanceFilter` to discriminate — `walking_distance.py` also needs a
        curated `city_center` reference point for the search location, same as
        `tests/core/test_geo_engine_integration.py` already proves for the geo
        engine. Seeding one here at exactly `demo-001`'s coordinates gives a real,
        computable proximity-score gradient across the fixture's 3 listings (their
        real coordinates are ~0 / ~0.54 / ~1.32 km away — see
        src/connectors/fixtures/demo_platform/listings.html), so a 0.9 minimum score
        keeps only the closest listing instead of excluding or admitting all 3.
        """
        with self.db.transaction() as conn:
            reference_data_repository.upsert_knowledge_entry(
                conn,
                KnowledgeEntry(
                    id=None, category="city_center", key="Example City",
                    value_json=json.dumps({"latitude": 39.4790, "longitude": -0.3500}),
                    source="manual", updated_at=datetime.now(timezone.utc),
                ),
            )

        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, filter_engine=FilterEngine())
        result = agent.run(SearchRequest(location="Example City", criteria={"walking_distance": 0.9}))

        self.assertEqual(len(result.apartments), 1)
        self.assertEqual(result.apartments[0].platform_listing_id, "demo-001")

    def test_public_transport_time_filter_discriminates_once_a_curated_reference_point_exists(self) -> None:
        """Same rationale as the walking_distance test above, for
        `PublicTransportTimeFilter` — `public_transport.py` needs its own curated
        `public_transport` reference stop, not `city_center`.
        """
        with self.db.transaction() as conn:
            reference_data_repository.upsert_knowledge_entry(
                conn,
                KnowledgeEntry(
                    id=None, category="public_transport", key="Example City",
                    value_json=json.dumps(
                        {"latitude": 39.4790, "longitude": -0.3500, "stop_name": "Example City Central Stop"}
                    ),
                    source="manual", updated_at=datetime.now(timezone.utc),
                ),
            )

        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, filter_engine=FilterEngine())
        result = agent.run(SearchRequest(location="Example City", criteria={"public_transport_time": 0.9}))

        self.assertEqual(len(result.apartments), 1)
        self.assertEqual(result.apartments[0].platform_listing_id, "demo-001")


if __name__ == "__main__":
    unittest.main()
