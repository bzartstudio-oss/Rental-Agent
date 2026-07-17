# 36 — Performance Baseline

Version 2.5 Step 17. A one-time, honestly-measured baseline — not a
micro-benchmark suite, and not a source of hard regression gates except
where explicitly noted. Measured on the development machine (Windows 11,
Python 3.13.14) against fully-isolated temp databases/fixtures, never the
real project database. Reproduce with the measurement script described
below; absolute numbers will vary by machine, but relative proportions
(e.g. "multi-platform is ~2x one-platform") should hold.

## Results

| Measurement | Time | Notes |
|---|---|---|
| Fresh database startup (`Database()` on a brand-new file) | 0.169s | Applies `schema.sql` + all 11 migrations |
| Existing (already-migrated) database startup | 0.006s | No migrations to apply — just connection + PRAGMA setup |
| Migration application, fresh DB | 0.141s | Included in "fresh database startup" above; isolated here for clarity |
| CLI import + argument-parser construction | 0.826s | Cold Python process start + full import graph (Playwright, Flask, etc.) — not a search |
| Dashboard response time (`GET /`) | 0.034s | Real Flask test client, real facade calls, empty database |
| API health response time (`GET /api/v1/health`) | 3.029s | See "Known Slow Path" below |
| One-platform search time (real `RentalResearchAgent.run()`, `demo_platform`) | 1.099s | Real Playwright fetch of a local fixture, full pipeline |
| Multi-platform search time (`demo_platform` + `demo_platform_two`) | 2.521s | ~2.3x one-platform — consistent with a second real Playwright fetch, not a fixed overhead |
| Ranking V2 time (`RankingEngineV2.rank()`, in-memory, already-collected apartments) | 0.0004s | Negligible — pure Python scoring, no I/O |
| Analysis Engine time (`AnalysisEngine.analyze()`) | 0.005s | Negligible |
| Monitoring/search comparison time (`compare_searches()`) | 0.004s | Negligible |
| Report generation time (`generate_report()`) | 0.004s | Negligible — plain string templating, no Jinja2 overhead (see docs/09) |
| Backup time (small fixture DB + no media/raw-pages) | 0.098s | Scales with data volume — SQLite's own online backup API |
| Restore time (same backup) | 0.032s | Scales with data volume |
| Database size after these deterministic fixture runs | 667,648 bytes (~652 KiB) | Two full search runs' worth of apartments/history/analysis/ranking data |

## Known Slow Path: `WebHealth.collect()` (~3s)

`GET /api/v1/health` (and the web dashboard's own `/health` page) calls
`WebHealth.collect()`, which calls `check_provider_health()` once per
registered `Provider` (Section "One real, additive change" in docs/32 is
unrelated — this is Step 8's own `providers/health.py`). Each check is fast
in isolation, but the AI providers' health check includes a real, short
network probe (e.g. Ollama's own reachability check) that can take up to a
couple of seconds when nothing is listening on that port. This is the same
generous-timeout tradeoff `tests/web/test_performance.py`'s own
`test_health_and_statistics_complete_quickly` already documents (a 5s bound,
not a tight one) — a process-startup-adjacent cost, not a per-request
latency budget regression. Not a bug; recorded here as a real, load-bearing
number a new developer should expect, not a surprise.

## Regression Thresholds (Only Where Stable and Meaningful)

Applied in the existing test suite, not newly invented for this document:

- `tests/web/test_performance.py::DashboardPerformanceTests` — dashboard
  snapshot on an empty database: **< 2.0s**; combined health+statistics:
  **< 5.0s** (see the note above for why this one is deliberately generous).
- `tests/web/test_performance.py::RouteResponseTimeTests` — `GET /`: **< 2.0s**.

No other measurement above has a codified regression threshold — search/
ranking/analysis/report timings are dominated by real Playwright I/O and
fixture size, which varies too much run-to-run on a shared CI machine to
make a tight, non-flaky gate meaningful (per the mission's own "do not make
timing tests flaky"). These numbers exist as a documented baseline to
compare future measurements against by eye, not as an automated gate.

## Reproducing This Baseline

The measurement script used to produce the table above is not part of the
permanent test suite (timing numbers, unlike correctness, aren't meaningful
as a pass/fail assertion at this granularity) — reproduce it by timing the
same calls directly, e.g.:

```python
import time
from src.storage.database import Database
started = time.perf_counter()
Database(db_path="/tmp/fresh.db")
print(time.perf_counter() - started)
```

## Related Documents

- [33_Release_Candidate_Acceptance.md](33_Release_Candidate_Acceptance.md)
- [35_Installation_and_Operations.md](35_Installation_and_Operations.md)
