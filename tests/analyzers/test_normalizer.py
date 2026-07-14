import unittest

from src.analyzers.normalizer import normalize
from src.connectors.base import RawListing


class NormalizerTests(unittest.TestCase):
    def test_trims_whitespace_and_lowercases_status(self) -> None:
        raw = RawListing(
            platform_listing_id=" listing-1 ",
            title="  Nice Place  ",
            price=1000.0,
            url=" https://example.com/1 ",
            status=" AVAILABLE ",
            address_raw="  123 Main St  ",
        )

        result = normalize(raw)

        self.assertEqual(result["platform_listing_id"], "listing-1")
        self.assertEqual(result["title"], "Nice Place")
        self.assertEqual(result["url"], "https://example.com/1")
        self.assertEqual(result["current_status"], "available")
        self.assertEqual(result["address_raw"], "123 Main St")

    def test_negative_price_is_clamped_to_zero(self) -> None:
        raw = RawListing(platform_listing_id="x", title="x", price=-50.0, url="https://example.com/x")
        self.assertEqual(normalize(raw)["current_price"], 0.0)


if __name__ == "__main__":
    unittest.main()
