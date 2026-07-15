"""Unit tests for src/connectors/sdk/validator.py — ConnectorValidator."""

import unittest

from src.connectors.base import RawListing
from src.connectors.sdk.validator import ConnectorValidator


def _listing(**overrides) -> RawListing:
    defaults = dict(platform_listing_id="l1", title="A Nice Place", price=1000.0, url="https://example.com/1")
    defaults.update(overrides)
    return RawListing(**defaults)


class ConnectorValidatorTests(unittest.TestCase):
    def test_a_fully_populated_listing_is_valid_with_no_warnings(self) -> None:
        result = ConnectorValidator.validate(_listing())
        self.assertTrue(result.is_valid)
        self.assertEqual(result.warnings, [])

    def test_missing_title_produces_a_warning(self) -> None:
        result = ConnectorValidator.validate(_listing(title=""))
        self.assertFalse(result.is_valid)
        self.assertEqual([w.field for w in result.warnings], ["title"])

    def test_blank_string_field_counts_as_missing(self) -> None:
        result = ConnectorValidator.validate(_listing(url="   "))
        self.assertFalse(result.is_valid)
        self.assertEqual([w.field for w in result.warnings], ["url"])

    def test_zero_price_is_a_valid_present_value(self) -> None:
        """0.0 is falsy in Python but a legitimate price — must not be flagged missing."""
        result = ConnectorValidator.validate(_listing(price=0.0))
        self.assertTrue(result.is_valid)

    def test_multiple_missing_fields_all_produce_warnings(self) -> None:
        result = ConnectorValidator.validate(_listing(title="", url=""))
        self.assertEqual({w.field for w in result.warnings}, {"title", "url"})

    def test_validate_all_processes_a_list(self) -> None:
        results = ConnectorValidator.validate_all([_listing(), _listing(title="")])
        self.assertEqual([r.is_valid for r in results], [True, False])


if __name__ == "__main__":
    unittest.main()
