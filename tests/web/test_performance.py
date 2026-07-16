"""Performance-regression smoke tests — see docs/32_Web_Dashboard.md
"System Health". Soft guards (generous bounds), not micro-benchmarks: catch
an accidental O(n^2) or an accidental synchronous full-table scan added to a
read-heavy page, not measure absolute speed.
"""

from __future__ import annotations

import time
import unittest

from src.web.facade import WebServiceFacade
from tests.web.helpers import web_test_app


class DashboardPerformanceTests(unittest.TestCase):
    def test_dashboard_snapshot_completes_quickly_on_an_empty_database(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            started = time.monotonic()
            facade.dashboard_snapshot("p1")
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 2.0, f"dashboard_snapshot took {elapsed:.2f}s on an empty database")

    def test_health_and_statistics_complete_quickly(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            started = time.monotonic()
            facade.system_health()
            facade.system_statistics()
            elapsed = time.monotonic() - started
            # More generous than the dashboard bound above: `system_health()`
            # calls `check_provider_health()` once per registered provider,
            # each doing a real (if fast) connectivity-style check — a
            # process-startup cost, not a per-request one, so a few seconds
            # here is a soft guard against an accidental O(n^2), not a tight
            # latency budget.
            self.assertLess(elapsed, 5.0, f"health/statistics took {elapsed:.2f}s")


class RouteResponseTimeTests(unittest.TestCase):
    def test_dashboard_route_responds_quickly(self) -> None:
        with web_test_app() as (app, db, tmp):
            client = app.test_client()
            started = time.monotonic()
            resp = client.get("/")
            elapsed = time.monotonic() - started
            self.assertEqual(resp.status_code, 200)
            self.assertLess(elapsed, 2.0, f"GET / took {elapsed:.2f}s")


if __name__ == "__main__":
    unittest.main()
