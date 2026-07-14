"""Data-integrity checks for the static seed list (discovery/known_platforms.py) and an
end-to-end proof that syncing it produces a sane registry — no live network calls, since
compiling this list didn't make any either (see its module docstring).
"""

import tempfile
import unittest
from pathlib import Path

from src.discovery.discovery_agent import DiscoveryAgent
from src.discovery.known_platforms import ALL_KNOWN_PLATFORMS, KNOWN_UNSUPPORTED_PLATFORMS, REFERENCE_CONNECTORS
from src.storage.database import Database


class KnownPlatformsDataIntegrityTests(unittest.TestCase):
    def test_no_duplicate_platform_ids(self) -> None:
        ids = [c.platform_id for c in ALL_KNOWN_PLATFORMS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_no_duplicate_homepages(self) -> None:
        homepages = [c.homepage.lower() for c in ALL_KNOWN_PLATFORMS]
        self.assertEqual(len(homepages), len(set(homepages)))

    def test_reference_connectors_are_marked_available_with_a_connector_name(self) -> None:
        for candidate in REFERENCE_CONNECTORS:
            self.assertTrue(candidate.connector_available, candidate.platform_id)
            self.assertIsNotNone(candidate.connector_name, candidate.platform_id)

    def test_known_unsupported_platforms_have_no_connector(self) -> None:
        for candidate in KNOWN_UNSUPPORTED_PLATFORMS:
            self.assertFalse(candidate.connector_available, candidate.platform_id)
            self.assertIsNone(candidate.connector_name, candidate.platform_id)

    def test_every_candidate_has_country_and_homepage(self) -> None:
        for candidate in ALL_KNOWN_PLATFORMS:
            self.assertTrue(candidate.country, candidate.platform_id)
            self.assertTrue(candidate.homepage, candidate.platform_id)


class KnownPlatformsSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.agent = DiscoveryAgent(self.db)

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_syncing_the_known_platform_list_registers_all_of_them(self) -> None:
        report = self.agent.sync_platforms(ALL_KNOWN_PLATFORMS)

        self.assertEqual(len(report.new_platforms), len(ALL_KNOWN_PLATFORMS))
        self.assertEqual(len(report.marked_unsupported), len(KNOWN_UNSUPPORTED_PLATFORMS))

        available = self.agent.discover(request=None)
        self.assertEqual({p.id for p in available}, {c.platform_id for c in REFERENCE_CONNECTORS})

    def test_syncing_twice_does_not_duplicate_or_error(self) -> None:
        self.agent.sync_platforms(ALL_KNOWN_PLATFORMS)
        second_report = self.agent.sync_platforms(ALL_KNOWN_PLATFORMS)  # must not raise

        self.assertEqual(second_report.new_platforms, [])
        self.assertEqual(len(second_report.updated_platforms), len(ALL_KNOWN_PLATFORMS))

        all_platforms = self.agent.load_platforms()
        self.assertEqual(len(all_platforms), len(ALL_KNOWN_PLATFORMS))  # still no duplicates


if __name__ == "__main__":
    unittest.main()
