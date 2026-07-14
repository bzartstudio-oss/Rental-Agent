"""Phase 3 exit-criteria test (docs/10_Roadmap.md): can fetch and persist a real page
into raw_pages/ storage, independent of any connector-level parsing.

`https://example.com` is IANA's reserved documentation/testing domain — safe and stable
to fetch in a test, unlike a real commercial rental site.
"""

import tempfile
import unittest
from pathlib import Path

from src.collectors import raw_page_store
from src.collectors.browser_collector import BrowserCollector


class RawPageStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self._tmp_dir.name)

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_save_page_writes_content_and_returns_path(self) -> None:
        path = raw_page_store.save_page("test_platform", "<html>hello</html>", base_dir=self.base_dir)

        self.assertTrue(path.exists())
        self.assertEqual(path.read_text(encoding="utf-8"), "<html>hello</html>")
        self.assertEqual(path.parent.name, "test_platform")

    def test_save_page_never_overwrites_a_previous_capture(self) -> None:
        first_path = raw_page_store.save_page("test_platform", "first", base_dir=self.base_dir)
        second_path = raw_page_store.save_page("test_platform", "second", base_dir=self.base_dir)

        self.assertNotEqual(first_path, second_path)
        self.assertEqual(first_path.read_text(encoding="utf-8"), "first")
        self.assertEqual(second_path.read_text(encoding="utf-8"), "second")

    def test_fetch_and_persist_a_real_page(self) -> None:
        """The actual Phase 3 exit criteria: a real Playwright fetch, really saved to disk."""
        with BrowserCollector() as browser:
            html = browser.fetch("https://example.com")

        path = raw_page_store.save_page("example_platform", html, base_dir=self.base_dir)

        self.assertTrue(path.exists())
        self.assertIn("Example Domain", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
