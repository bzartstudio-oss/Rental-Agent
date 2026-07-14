"""Real fetch against https://example.com — IANA's reserved documentation/testing
domain, safe and stable to hit in a test.
"""

import unittest

from src.collectors import http_collector


class HttpCollectorTests(unittest.TestCase):
    def test_fetch_text_returns_real_page_content(self) -> None:
        text = http_collector.fetch_text("https://example.com")
        self.assertIn("Example Domain", text)


if __name__ == "__main__":
    unittest.main()
