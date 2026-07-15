"""Certifies RentCastConnector against the SDK contract, per
docs/18_Connector_SDK.md "Certification Requirements" — the same mixin every connector
(demo or production) is certified with, no RentCast-specific certification logic. The
only RentCast-specific code in this whole module is `setUp`/`tearDown`: a fake API key
(env var) and a mocked HTTP layer, so `self.connector_class()` — instantiated with no
arguments by the mixin itself — has everything it needs to complete a real
`search()` call without a real network request or a real API key.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.connectors.rentcast.connector import RentCastConnector
from src.search.search_request import SearchRequest
from tests.connectors.sdk.certification import ConnectorCertificationMixin
from tests.support import isolated_collectors

_FIXTURE_PATH = Path(__file__).parent.parent.parent.parent / "src" / "connectors" / "rentcast" / "fixtures" / "sample_response.json"
_FIXTURES = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


class RentCastConnectorCertificationTests(ConnectorCertificationMixin, unittest.TestCase):
    connector_class = RentCastConnector
    search_request = SearchRequest(location="Austin, TX")

    def setUp(self) -> None:
        self._env = patch.dict(os.environ, {"RENTCAST_API_KEY": "certification-test-key"}, clear=True)
        self._env.__enter__()

        self._tmp_dir = tempfile.TemporaryDirectory()
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

        self._client_patch = patch("src.connectors.rentcast.connector.RentCastClient")
        mock_client_cls = self._client_patch.start()
        mock_client_cls.return_value.get_rental_listings.return_value = [
            _FIXTURES["full_listing"],
            _FIXTURES["missing_coordinates_listing"],
        ]

    def tearDown(self) -> None:
        self._client_patch.stop()
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()
        self._env.__exit__(None, None, None)


if __name__ == "__main__":
    unittest.main()
