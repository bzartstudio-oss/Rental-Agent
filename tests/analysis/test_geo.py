"""Unit tests for src/analysis/geo.py — pure haversine math, no database, no network."""

import unittest

from src.analysis.geo import haversine_km


class HaversineKmTests(unittest.TestCase):
    def test_distance_from_a_point_to_itself_is_zero(self) -> None:
        self.assertAlmostEqual(haversine_km(40.0, -3.0, 40.0, -3.0), 0.0, places=6)

    def test_one_degree_of_latitude_is_about_111_km(self) -> None:
        distance = haversine_km(0.0, 0.0, 1.0, 0.0)
        self.assertAlmostEqual(distance, 111.19, delta=0.5)

    def test_known_distance_madrid_to_barcelona(self) -> None:
        # Real-world reference distance, ~504 km straight-line.
        distance = haversine_km(40.4168, -3.7038, 41.3874, 2.1686)
        self.assertAlmostEqual(distance, 504, delta=5)

    def test_is_symmetric(self) -> None:
        a_to_b = haversine_km(40.0, -3.0, 41.0, -2.0)
        b_to_a = haversine_km(41.0, -2.0, 40.0, -3.0)
        self.assertAlmostEqual(a_to_b, b_to_a, places=9)


if __name__ == "__main__":
    unittest.main()
