# Changelog

All notable changes to this project. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/) — dates are when the change was made,
not a formal release date (this project doesn't cut releases yet).

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
