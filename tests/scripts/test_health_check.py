"""Tests for `scripts/health_check.py` — see
docs/35_Installation_and_Operations.md "Health Check".
"""

from __future__ import annotations

import unittest

from scripts.health_check import CheckResult, run_all_checks


class HealthCheckTests(unittest.TestCase):
    def test_every_check_returns_a_real_status(self) -> None:
        results = run_all_checks()
        self.assertTrue(results)
        for result in results:
            self.assertIsInstance(result, CheckResult)
            self.assertIn(result.status, ("PASS", "WARN", "FAIL"))
            self.assertTrue(result.detail)

    def test_python_version_check_passes_on_the_current_interpreter(self) -> None:
        results = run_all_checks()
        python_check = next(r for r in results if r.name == "python_version")
        self.assertEqual(python_check.status, "PASS")

    def test_expected_check_names_are_all_present(self) -> None:
        results = run_all_checks()
        names = {r.name for r in results}
        for expected in (
            "python_version", "dependencies", "playwright_browsers", "configuration",
            "writable_data_directories", "database_accessibility", "migration_status",
            "web_binding", "connector_registry", "provider_registry", "geographic_providers",
            "notification_channels", "storage_availability",
        ):
            self.assertIn(expected, names)


if __name__ == "__main__":
    unittest.main()
