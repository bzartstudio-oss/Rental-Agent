import json
import unittest

from src.search.search_request import SearchRequest


class SearchRequestTests(unittest.TestCase):
    def test_requires_location(self) -> None:
        with self.assertRaises(ValueError):
            SearchRequest(location="")

    def test_rejects_invalid_criteria_at_construction(self) -> None:
        with self.assertRaises(KeyError):
            SearchRequest(location="Example City", criteria={"not_a_real_filter": 1})

    def test_assigns_a_unique_id_by_default(self) -> None:
        first = SearchRequest(location="Example City")
        second = SearchRequest(location="Example City")
        self.assertNotEqual(first.id, second.id)

    def test_to_criteria_json_round_trips(self) -> None:
        request = SearchRequest(location="Example City", criteria={"max_price": 1200.0})

        parsed = json.loads(request.to_criteria_json())

        self.assertEqual(parsed["location"], "Example City")
        self.assertEqual(parsed["criteria"], {"max_price": 1200.0})


if __name__ == "__main__":
    unittest.main()
