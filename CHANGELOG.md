# Changelog

All notable changes to this project. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/) — dates are when the change was made,
not a formal release date (this project doesn't cut releases yet).

## [2.0.3] — 2026-07-14 — Search Memory & Comparison Engine

Third step of the Version 2.0 implementation (see `docs/10_Roadmap.md` "Implementation Order").

### Added
- `src/search_memory/` — the Search Memory & Comparison Engine: `models.py`
  (`SearchExecution`, `SearchComparison`, `SearchStatistics`, `SearchTimeline`,
  `ApartmentPriceChange`, `ApartmentAvailabilityChange`, `PlatformCoverageChange`),
  `comparison.py` (pure `diff_apartment_sets`, `platform_coverage_change`,
  `search_quality`), `search_memory_service.py` (`record_completed_search`,
  `latest_search`, `search_history`, `search_timeline`, `compare_searches`,
  `average_execution_time`, `average_apartment_count`, `search_statistics`).
- `storage/search_memory_repository.py` — `search_observed_apartments` data access,
  `complete_search_execution` (the run-stats completion `UPDATE` on
  `search_requests`), `find_previous_search`, `get_search_history`.
- `storage/search_repository.py` gained a shared `row_to_search_request()` helper.
- `analyzers/engine.py` now writes a `search_observed_apartments` row for every
  processed listing.
- `RentalResearchAgent.run()` now times itself, tracks discovered vs. successfully
  searched platforms and each connector failure's exception message, and calls
  `record_completed_search()` automatically after report generation — every search
  now permanently remembers its own full execution, with no manual wiring.
- 34 new tests (156 total): comparison unit tests, service-level tests (including
  the run-over-run comparison scenario and repeated-search/append-only regression
  tests), repository round-trip tests, and a new core-agent integration test file.

### Fixed
- A real bug in the run-over-run "changed" comparison, found by running the actual
  CLI twice against the same unchanged data (not just unit tests): the original
  timestamp-window design counted a search's *own* initial-observation writes as
  changes relative to itself, since those writes happen strictly after that search's
  `created_at` (processing takes real time). Fixed by bounding the comparison by
  `search_id` identity first. See `docs/17_Search_Memory.md` "A Real Bug".
- A pre-existing doc typo: `docs/03_Data_Model.md` said "eight new columns" for the
  Search Memory `search_requests` extension; it's nine — corrected.

### Not included (explicitly deferred to later Version 2.0 steps)
- No Knowledge Engine logic (`platform_performance_observations`, Platform
  Intelligence rollups) — schema only, as before.
- No AI or predictive logic anywhere in this engine — every figure is a plain
  average or set/timestamp comparison over already-stored data.

## [2.0.2] — 2026-07-14 — Apartment History Engine

Second step of the Version 2.0 implementation (see `docs/10_Roadmap.md` "Implementation Order").

### Added
- `src/history/` — the Apartment History Engine: `models.py` (`Change`/`ChangeType`,
  the structured comparison result every method below produces), `comparison.py`
  (pure functions: `compare_price`, `compare_availability`, `compare_title`,
  `compare_description`, `compare_coordinates`, `compare_images`, `compare_presence`,
  `summarize_listing_updated`), `history_service.py` (`record_new_apartment`,
  `record_reobservation`, `latest_version`, `previous_version`, `price_timeline`,
  `availability_timeline`, `change_timeline`).
- `storage/apartment_history_repository.py` — data access for `apartment_change_log`
  and `apartment_image_events` (schema already existed since migration 0001; this adds
  the first real reads/writes).
- `storage/apartment_repository.py`: `update_apartment_details` (title/description),
  `mark_image_not_current`.
- `connectors/base.py`'s `RawListing` and `analyzers/normalizer.py` gained
  `description`.
- `analyzers/engine.py`'s write sequence now also writes `apartment_change_log` rows
  for title/description changes and runs Image Change Detection — one unified
  `_sync_images` function replacing the old `_collect_images`, used for both new and
  re-observed apartments (a new apartment has no prior images, so every URL is
  naturally "added," in original order — behavior-identical to before).
- 43 new tests (122 total): comparison unit tests, history-service tests (including a
  reconstructed-`previous_version` test and a 500-row change-timeline performance
  test), repository round-trip tests, engine-level regression/integration tests.

### Fixed
- Nothing was tracking title/description/image changes before this — a listing's
  title being edited, or a photo being added or removed, was invisible; only its
  current value was known, with no way to see it change over time. Now every such
  change is appended to `apartment_change_log`/`apartment_image_events`, never
  overwritten.

### Not included (explicitly deferred to later Version 2.0 steps)
- `compare_coordinates` and `compare_presence` ("listing removed"/"listing returned")
  are implemented and unit-tested but not wired into the pipeline: no connector
  populates coordinates yet (Step 7), and "removed" needs Search Memory's
  full-observed-set comparison (Step 3) to mean "gone from the platform" rather than
  "excluded by this run's filters."
- No Knowledge Engine logic, no Search Memory (`search_observed_apartments`, run-stats
  columns) — schema only, as before.

## [2.0.1] — 2026-07-14 — Migration Framework

First step of the Version 2.0 implementation (see `docs/10_Roadmap.md` "Implementation Order").

### Added
- `storage/migrations/` — numbered SQL migration files, applied automatically on startup.
- `schema_migrations` tracking table, so a migration never runs twice.
- `storage/migrations/0001_v2_knowledge_engine.sql` — the entire Version 2.0 schema
  designed on 2026-07-14: 6 new tables (`apartment_change_log`, `apartment_image_events`,
  `search_observed_apartments`, `platform_performance_observations`,
  `filter_definitions`, `apartment_analysis_metrics`) and new nullable columns on
  `platforms` (+6), `apartments` (+1), `apartment_images` (+2), `search_requests` (+9).
- New fields on the `Platform`, `Apartment`, `ApartmentImage`, and `SearchRequestRecord`
  dataclasses, and corresponding read/write updates in `discovery/platform_registry.py`,
  `storage/apartment_repository.py`, `storage/search_repository.py`.
- Migration framework tests: migrating a pre-migration database in place, idempotent
  repeated startup, failed-migration rollback, and version-ordered (not alphabetical)
  application.

### Fixed
- The database no longer needs to be deleted and regenerated for a schema change — the
  v1.1 `platforms` rework required a reset; this migration, and every additive one after
  it, does not. See `learning/database_notes.md`.
- A real transactional-DDL bug found while building the rollback test: Python's
  `sqlite3` module doesn't implicitly open a transaction before `CREATE`/`ALTER`
  statements the way it does for `INSERT`/`UPDATE`, so a failed migration's earlier
  `CREATE TABLE` was committing immediately regardless of a later `rollback()` call. Fixed
  by having the migration runner manage its own explicit `BEGIN`/`COMMIT`/`ROLLBACK`
  transaction rather than relying on the driver's implicit-transaction heuristic. See
  `learning/python_notes.md`.

### Not included (explicitly deferred to later Version 2.0 steps)
- No business logic for the 6 new tables — Apartment History, Search Memory, the
  Knowledge Engine, the Dynamic Filter Engine, and the Deep Analysis Engine are schema
  only in this step. Nothing writes to `platform_performance_observations`,
  `apartment_change_log`, etc. yet.

## [2.0] — 2026-07-14 — Autonomous Rental Intelligence Platform (design)

Architecture-only — no code changes. Full design across `docs/00`, `docs/03`–`docs/07`,
and three new docs (`docs/15_Agent_Architecture.md`, `docs/16_Knowledge_Engine.md`,
`docs/17_Search_Memory.md`). See `docs/10_Roadmap.md` "Version 2.0" for the complete
scope: Knowledge Engine, Apartment History, Search Memory, Platform Intelligence, Dynamic
Filter Engine, Deep Analysis Engine, Connector SDK, and the multi-agent naming convention.
An 8th core principle was added: learning happens through data, never by rewriting code.

## [1.1] — 2026-07-14 — Multi-Platform Discovery Framework

- Reworked the `platforms` table: `country`, `supported_cities`, `rental_types`,
  `homepage`, `search_url`, `requires_login`, `connector_available`, `connector_name`,
  `last_verified`, `discovery_method` replace `base_url`/`connector_module`/`is_active`.
- `DiscoveryAgent.sync_platforms()` — load existing platforms, detect duplicates (exact
  id or normalized homepage domain), update metadata, save new platforms, mark
  unsupported ones without deleting them.
- `discovery/known_platforms.py` — 2 reference connectors plus 6 real, well-known rental
  platforms across 4 countries, catalogued as `connector_available = False`.
- `ui/cli.py` syncs the known-platforms list on every startup.

## [1.0] — 2026-07-14 — Rental Intelligence Platform, V1.0

The full pipeline, end-to-end, proven against two reference connectors
(`demo_platform`, `demo_platform_two`) rather than a real commercial site, since no real
platform target had been chosen yet:

- Storage foundation: SQLite schema, repositories, versioned price/availability history.
- Platform Registry + Discovery Agent (static registry).
- Collectors (browser/HTTP fetch, image download, raw-page persistence).
- Connector contract, the Analysis Engine (normalize/dedupe/change-detect/enrich),
  and `RentalResearchAgent` — the real orchestrator.
- Ranking Engine (extensible criteria registry) and an HTML Report Generator.
- `ui/cli.py` — the real entry point.
- Re-run/compare proof: a second search after a real data change accumulates history
  instead of overwriting it.
- A second connector, with a deliberately different page structure, proving the
  platform-independence boundary holds without touching other modules.

## [0.1] — 2026-07-12 — Working prototype before platform architecture

Early prototype work predating the documented architecture — a config-driven search
concept (`config/settings.json`), a basic `Apartment`/`Configuration` model, and a
Playwright browser-launch stub. Confirmed stale and superseded once the V1.0 architecture
was designed; not migrated forward. See `learning/architecture_notes.md`.
