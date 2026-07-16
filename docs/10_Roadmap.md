# 10 — Roadmap

Status: **V1.0 (7 phases) + v1.1 (Multi-Platform Discovery Framework) live in code and tested, as of 2026-07-14.** Version 2.0 is fully designed; **Implementation Steps 1–7 are done** — Migration Framework (Sprint V2.0.1), Apartment History Engine (Step 2), Search Memory & Comparison Engine (Step 3), the Knowledge Engine (Step 4), an architecture cleanup pass (Step 4.5), the Connector SDK & Plugin Framework (Step 5), the Deep Analysis Engine (Step 6, 314 tests), and the First Production Connector — RentCast (Step 7, 361 tests). **Step 6 was built ahead of the originally-planned Step 7** (Dynamic Filter Engine) at explicit instruction; **Step 7 was then reassigned again**, this time to the First Production Connector — pulling forward the item "After v2.0: Still the Same Answer" (below) had deferred to *after* v2.0 entirely, at the user's explicit instruction. Dynamic Filter Engine is pushed to Step 8, still fully designed, not yet implemented. On top of the numbered steps, a separate, unnumbered **Provider Abstraction Layer** (`src/providers/`, 413 tests total) was added afterward, then validated (SDK Validation Sprint, 428 tests) and reviewed (Production Readiness Review, docs/23, no code changed). **Version 2.5** is a new, explicitly separate version built on top of all of the above: **Step 8 — Production Provider Framework** (done, 460 tests), **Step 9 — Dynamic Filter Engine** (done, 562 tests), which also fulfills the Version 2.0 Step 8 slot's original intent, **Step 10 — Geographic Intelligence Engine** (done, 640 tests), **Step 11 — Intelligent Ranking Engine V2** (done, 734 tests), and **Step 12 — User Feedback and Preference Learning Engine** (done, 864 tests total) — see all five sections below. The numbered list reflects the order things actually happened in, not the original sequencing; see each reordered step's entry for the reasoning. See "Version 2.0"/"Version 2.5" below. Update this as priorities shift — it should always reflect current reality, not the original plan.

## Reference Connector Strategy

No real rental platform had been chosen when Phases 3–7 were built (the "which platform first" question in [../notes/Questions.md](../notes/Questions.md) was still open). Rather than block architecture completion on that product decision, or unilaterally pick a real commercial site to scrape without confirming its ToS, every phase from here on was proven against **`demo_platform`** and **`demo_platform_two`** — real `Connector` implementations that fetch real local HTML fixtures via a real Playwright browser and parse them with BeautifulSoup, exactly like a connector for a live site would, but touching no external service. This is explicitly not a shortcut around the exit criteria — every fetch, parse, database write, and report generation described below is real; only the *source* is a controlled fixture instead of a commercial website. Swapping in a real platform means writing one more connector implementing the same contract (see [06_Connector_Framework.md](06_Connector_Framework.md)) — nothing else changes, which Phase 7 exists specifically to demonstrate.

**Resolved in v2.0 Step 7 (2026-07-15): RentCast.** See [20_First_Production_Connector.md](20_First_Production_Connector.md) for the full write-up — a real, developer-facing REST API verified (not assumed) to have self-service auth, a free tier, and Terms of Use permitting this kind of programmatic access, chosen over the 6 previously-catalogued platforms (Zillow, Apartments.com, Rightmove, Idealista, Fotocasa, ImmoScout24), none of which offer a comparable self-service path and all of which prohibit scraping. `demo_platform`/`demo_platform_two` remain in place as the reference fixtures every future connector is still developed and certified against before touching a live source.

## Why This Order

Storage comes first, before any pipeline logic, because every other module either writes to it or reads from it — building connectors or ranking against a schema that doesn't exist yet would mean building twice. The first connector comes before a second one on purpose too: Phase 4 exists specifically to prove the Connector/Collector abstraction against one real, messy website before investing in a second, so any abstraction mistakes get fixed once instead of twice.

## Phase 0 — Foundations (done)

Repo scaffolded, working agreement established, documentation structure in place (this doc set), Python environment + Playwright/Chromium installed, rental type and `data/` layout decided.

## Phase 1 — Storage Foundation (done, 2026-07-14)

- `storage/schema.sql` implementing every table in [03_Data_Model.md](03_Data_Model.md)
- `storage/database.py` connection management, `storage/models.py` dataclasses
- `storage/apartment_repository.py`, `search_repository.py`, `knowledge_repository.py`
- Executed the legacy-folder reconciliation in [02_Folder_Guide.md](02_Folder_Guide.md) — with one change from the original plan: `apartment.py`/`config_loader.py` were **deleted, not migrated**, once confirmed stale (they modeled a different, narrower concept); `storage/models.py` and `core/config.py` were written fresh against the confirmed schema instead. `browser_manager.py` did move into `collectors/browser_collector.py` as planned.
- Also fixed along the way: `requirements.txt` was empty despite the venv having real dependencies installed — frozen from the actual environment.
- Exit criteria met: `tests/storage/test_apartment_repository.py` proves a hand-crafted `Apartment` round-trips through insert/read, and that re-observing it with a changed price adds a new history row without losing the original (Principles 1 & 3, in running code).

## Phase 2 — Platform Registry + Discovery Agent (done, 2026-07-14)

- `discovery/platform_registry.py`, `discovery/discovery_agent.py`
- Exit criteria met: `tests/discovery/test_discovery_agent.py` proves `DiscoveryAgent.discover(request)` returns a registered active platform and excludes inactive ones. **Note:** this is proven with a test-registered platform, not a real seed row in `data/rental_intelligence.db` — the actual first platform is still an open question (see [../notes/Questions.md](../notes/Questions.md)), so nothing fictional was seeded into the real database.

## Phase 3 — Collectors (done, 2026-07-14)

- `collectors/browser_collector.py` (the promoted `browser_manager.py`), `collectors/raw_page_store.py`, `collectors/image_collector.py`, plus `collectors/http_collector.py` (not originally listed, added for completeness per docs/02)
- Exit criteria met: `tests/collectors/test_raw_page_store.py::test_fetch_and_persist_a_real_page` does a real Playwright fetch of `https://example.com` (IANA's reserved test domain) and really saves it to disk

## Phase 4 — First Connector, End-to-End (done, 2026-07-14)

- `connectors/base.py` (Connector contract + `RawListing`), `connectors/demo_platform.py` (see "Reference Connector Strategy" above)
- `search/search_request.py` + `search/criteria.py` (extensible filter registry: `max_price`, `min_price`, `min_bedrooms`, `min_bathrooms`, `min_sqft`)
- `analyzers/normalizer.py`, `deduplicator.py`, `change_detector.py`, `enricher.py`, and `analyzers/engine.py` (an addition not in the original file list — composes the other four into the write sequence from [07_Analysis_Engine.md](07_Analysis_Engine.md); needed because that composition has to live somewhere and core/agent.py must not contain per-listing business logic)
- `core/agent.py` (`RentalResearchAgent`) — sequences Discovery → Connector → Analysis, isolates a broken connector so it doesn't abort the whole run
- Exit criteria met: `tests/core/test_agent.py` — a real `SearchRequest` run through the real orchestrator against the real `demo_platform` connector produces real rows in `apartments`/`apartment_price_history`/`apartment_availability_history`/`apartment_images`

## Phase 5 — Ranking + Reports (done, 2026-07-14)

- `ranking/ranking_engine.py`, `ranking/scoring.py` (weighted-sum, reusing the same filter registry as `search/criteria.py`)
- `services/report_generator.py` — plain Python string templating, not Jinja2 (it isn't an installed dependency and V1's layout doesn't need a templating engine — resolves the "proposal, not yet locked in" note in [09_Report_System.md](09_Report_System.md))
- `core/agent.py` extended to write `search_results` rows and call the report generator
- `ui/cli.py` — the real V1 entry point; `src/rental_agent.py` now delegates to it (previously a leftover OpenAI-key status check from before this architecture existed — retired, see [../learning/architecture_notes.md](../learning/architecture_notes.md))
- Exit criteria met: `tests/ui/test_cli.py` runs the CLI end-to-end and gets a real `output/<search_id>.html` with real prices, images, original URLs, and score breakdowns. **Also run for real once** (not just in tests) against the actual project `data/`/`output/` folders — see the dev journal.

## Phase 6 — Re-run & Compare (done, 2026-07-14)

- No new modules — this phase is a test proving Phases 1–5 actually behave correctly together, not new code
- Exit criteria met: `tests/core/test_reproducibility.py` edits the real fixture in place to simulate a price change, re-runs the same search through the real orchestrator, and confirms `apartment_price_history` gets a second row without losing the first, and that each search's `search_results` snapshot keeps the price *as observed at that search* even after the second run changes the live data

## Phase 7 — Second Connector (done, 2026-07-14)

- `connectors/demo_platform_two.py` — a genuinely different fixture shape (table/tr/td markup, different class names, `data-id` instead of `data-listing-id`) than `demo_platform.py`, specifically so parsing couldn't be copy-pasted
- Exit criteria met: `tests/core/test_multi_platform.py` — added with zero changes to `analyzers/`, `ranking/`, `storage/`, or `services/` (verifiable directly: no commit touching this phase modifies those folders); both platforms contribute results to one search

## Version 1.1 — Multi-Platform Discovery Framework (done, 2026-07-14)

Explicitly *not* a real connector yet — see [05_Platform_Discovery.md](05_Platform_Discovery.md)
for the full design. Built on top of the completed v1.0 architecture:

- Extended the `platforms` table with `country`, `supported_cities`, `rental_types`,
  `homepage`, `search_url`, `requires_login`, `connector_available`, `connector_name`,
  `last_verified`, `discovery_method` — replacing `base_url`/`connector_module`/`is_active`.
- `DiscoveryAgent.sync_platforms()` implements all 5 required behaviors: load existing,
  detect duplicates (exact id or normalized homepage domain), update metadata, save new
  platforms, mark unsupported ones (kept in the registry, not dropped — Principle 1).
- `discovery/known_platforms.py` seeds two reference connectors (`connector_available =
  True`) plus **6 real, well-known rental platforms across 4 countries** (Zillow,
  Apartments.com, Rightmove, Idealista, Fotocasa, ImmoScout24) as
  `connector_available = False` — real names/homepages, no live scraping to compile them.
- `ui/cli.py` now calls `sync_platforms()` on every startup instead of a one-off manual
  registration — the registry stays current automatically.
- 17 new tests (73 total), including exercising `sync_platforms()` against the real seed
  list. Verified with a real CLI run: 8 platforms registered, 2 available, 6 unsupported,
  6 listings processed from the 2 available platforms.
- Schema change meant deleting the existing dev `data/rental_intelligence.db` (no
  migrations framework yet — see [../learning/database_notes.md](../learning/database_notes.md))
  and letting it regenerate.

## Version 2.0 — Autonomous Rental Intelligence Platform (designed, 2026-07-14 — not yet implemented)

Full design: [00_Project_Vision.md](00_Project_Vision.md) Mission,
[03_Data_Model.md](03_Data_Model.md) (schema),
[04](04_Search_Request.md)/[05](05_Platform_Discovery.md)/[06](06_Connector_Framework.md)/[07](07_Analysis_Engine.md)
(extended), [15](15_Agent_Architecture.md)/[16](16_Knowledge_Engine.md)/[17](17_Search_Memory.md) (new).
Per explicit instruction: this is architecture only — no connectors, no `src/` code
changes yet. What follows is the migration plan and implementation order for when
building starts.

### Migration Plan (done, 2026-07-14 — Sprint V2.0.1)

**This is the first schema change that gets a real migrations mechanism**, rather than
another "delete the dev database and let it regenerate" (what v1.1 did — acceptable
there because the changed columns had no real data yet; not acceptable going forward,
per "must NEVER lose information from previous searches" and "assume hundreds of
thousands of records").

1. **`storage/migrations/`** — numbered SQL files, plus a `schema_migrations` table
   (`version INTEGER PK`, `applied_at TEXT`) tracking which have run.
   `storage/database.py` runs `schema.sql` (unchanged, still idempotent via `CREATE
   TABLE IF NOT EXISTS`), then discovers every migration file, sorts by **numeric**
   version (not filesystem/alphabetical order — `0002` must run before `0010`), and
   applies whichever aren't yet in `schema_migrations`, each in its own real transaction.
2. **`0001_v2_knowledge_engine.sql`** — the entire v2.0 change set in one migration:
   - 6 new tables via `CREATE TABLE IF NOT EXISTS`: `apartment_change_log`,
     `apartment_image_events`, `platform_performance_observations`,
     `filter_definitions`, `apartment_analysis_metrics`, `search_observed_apartments`.
   - `ALTER TABLE ADD COLUMN` for every new column on existing tables — all nullable or
     defaulted, so existing rows need no backfill: `platforms` (+6 columns —
     corrected from this doc's original "+7," `docs/03_Data_Model.md` was always the
     accurate count), `apartments` (+1: `description`), `apartment_images` (+2:
     `thumbnail_path`, `is_current` default `1`), `search_requests` (+9 — corrected
     from "+8" here for the same reason).
3. **Why this one is backward-compatible and the v1.1 one wasn't:** v1.1 dropped/renamed
   columns (`base_url` → `homepage`/`search_url`, `is_active` removed) — genuinely
   incompatible with old rows, hence the reset. v2.0 only *adds* nullable columns and new
   tables — old code paths that don't know about them keep working unmodified.
   **Verified against the real dev database**, not just tests: ran the actual CLI
   against `data/rental_intelligence.db` (containing real v1.1 data — 8 platforms from
   prior real runs) and confirmed it migrated in place with zero data loss. No dev-db
   reset needed, as designed.
4. **Code changes that rode along with the migration**: `storage/models.py`'s
   `Platform`/`Apartment`/`ApartmentImage`/`SearchRequestRecord` dataclasses gained the
   new fields; `discovery/platform_registry.py`, `storage/apartment_repository.py`, and
   `storage/search_repository.py` were updated to read/write them. No business logic for
   the 6 new tables was built — that's later steps' scope (see below).
5. **A real bug found and fixed while testing the rollback path**: Python's `sqlite3`
   doesn't implicitly open a transaction before DDL (`CREATE`/`ALTER`) the way it does
   for DML, so a naive `conn.execute()`-per-statement approach inside the existing
   `Database.transaction()` helper silently failed to roll back a failed migration's
   earlier statements. Fixed with an explicit `BEGIN`/`COMMIT`/`ROLLBACK` transaction
   specific to the migration runner. Full writeup in `learning/python_notes.md`. This is
   exactly why "wrap every migration in its own transaction" was tested with a
   deliberately-failing migration, not assumed correct from the happy path.

79 tests passing (73 existing untouched + 6 new migration tests: from-v1-database,
repeated-startup idempotency, failed-migration rollback, numeric ordering).

### Implementation Order

Sequenced by dependency, not by requirement number — schema first, then whatever's
self-contained, ending with the one piece that has an unresolved external dependency:

1. **Migrations framework + v2.0 schema** (above) — everything else depends on it existing first. **Done, 2026-07-14 (Sprint V2.0.1).**
2. **Apartment History extensions** (`apartment_change_log`, `apartment_image_events`) —
   a direct, self-contained extension of the existing, working `analyzers/engine.py`
   write sequence. **Done, 2026-07-14 (v2.0 Step 2).** New `src/history/` package
   (`models.py`'s `Change`/`ChangeType`, `comparison.py`'s pure per-field comparisons,
   `history_service.py`'s write + read-side timeline/version reconstruction) plus
   `storage/apartment_history_repository.py`. `RawListing`/`normalizer.py` gained
   `description`; `apartment_repository.py` gained `update_apartment_details` and
   `mark_image_not_current`. Image Change Detection is one unified function
   (`analyzers/engine.py::_sync_images`) used for both new and re-observed apartments.
   Verified against the real dev database, not just tests: edited `demo_platform`'s
   fixture title, ran the real CLI, confirmed a real `apartment_change_log` row with
   correct old/new values, then reverted the fixture and ran again, confirming the
   reversion was appended as a second row without disturbing the first. 43 new tests
   (122 total: 79 existing untouched + 43 new). Deliberate scope calls: title/
   description/coordinates/image comparison logic lives in the new `src/history/`
   package rather than being split into `analyzers/change_detector.py` as this doc
   originally sketched (price/status keep using `change_detector.py` unchanged);
   `compare_coordinates` and `compare_presence` ("listing removed"/"listing returned")
   are implemented and unit-tested but not wired into the pipeline, since nothing
   populated coordinates at the time (the "Step 7" this note originally meant was the
   Dynamic Filter Engine slot, before that number was reassigned — see Step 7's actual
   entry above; RentCast now does populate coordinates, but wiring `compare_coordinates`
   into the pipeline itself remains undone, out of scope for that connector sprint) and
   "removed" requires Search Memory's full-observed-set comparison (Step 3) to mean
   what the mission intends rather than "excluded by this run's filters." Full writeup
   in `learning/architecture_notes.md`.
3. **Search Memory** (`search_observed_apartments`, `search_requests` run-stats columns,
   run-over-run comparison) — needed before Knowledge Engine, since Knowledge Engine
   observations are keyed by `search_id` and conceptually "when did this search finish."
   **Done, 2026-07-14 (v2.0 Step 3).** New `src/search_memory/` package (`models.py`'s
   `SearchExecution`/`SearchComparison`/`SearchStatistics`/`SearchTimeline`,
   `comparison.py`'s pure `diff_apartment_sets`/`platform_coverage_change`/
   `search_quality`, `search_memory_service.py`'s write-side
   `record_completed_search` + read-side `latest_search`/`search_history`/
   `search_timeline`/`compare_searches`/`average_execution_time`/
   `average_apartment_count`/`search_statistics`) plus new
   `storage/search_memory_repository.py`. `RentalResearchAgent.run()` now times
   itself, tracks discovered/searched platform ids and connector exceptions, and calls
   `record_completed_search()` after report generation — automatically, for every run.
   `analyzers/engine.py` now writes a `search_observed_apartments` row for every
   listing processed (new capability; Step 2 didn't touch this table). 34 new tests
   (156 total: 122 existing untouched + 34 new).

   **A real bug found and fixed, not just designed around**: the originally-designed
   "changed since the previous run" comparison used a raw `observed_at` timestamp
   window, which broke the moment it ran against the real pipeline (not hand-picked
   test timestamps) — a search's own initial-observation writes happen strictly after
   its `SearchRequest.created_at` (processing takes real time), so they fell inside the
   *next* search's comparison window and were wrongly counted as changes. Fixed by
   bounding the comparison by `search_id` identity first, falling back to timestamp
   only for entries outside the two searches being compared. Caught by running the
   real orchestrator twice against the real `demo_platform` connector and seeing every
   apartment falsely reported as "changed" on an unchanged second run — full writeup
   in `docs/17_Search_Memory.md` and `learning/architecture_notes.md`.

   Verified against the real dev database, not just tests: ran the CLI twice
   back-to-back (second run correctly reported 0 new/removed/changed against 12
   accumulated `search_observed_apartments` rows across both runs), then edited
   `demo_platform`'s fixture price, ran a third time, and confirmed
   `search_memory_service.compare_searches()` reported the exact real price delta
   before reverting the fixture.
4. **Knowledge Engine + Platform Intelligence rollups** — depends on Search Memory's
   `search_id`/timing being solid; this is the "self-improving" mechanism, worth landing
   before more platforms/connectors get added so every connector built afterward is
   automatically tracked from its first run. **Done, 2026-07-14 (v2.0 Step 4).** New
   `src/knowledge/` package (`models.py`'s `PlatformKnowledge`/`ConnectorHealth`/
   `CityKnowledge`/`KnowledgeSummary`, `metrics.py`'s pure per-observation metric
   functions, `knowledge_service.py`'s write-side `record_platform_observation` +
   read-side `best_platforms`/`platform_reliability`/`connector_health`/
   `average_city_price`/`knowledge_summary`/`platform_statistics`/`city_statistics`)
   plus new `storage/platform_intelligence_repository.py` and
   `discovery/platform_registry.py::update_platform_rollups`. `RentalResearchAgent.run()`
   now captures per-platform metrics right after each connector call (success or
   failure) and records the complete observation — after ranking and after Search
   Memory's completion, per the mission's explicit Apartment History -> Search Memory
   -> Knowledge Engine ordering. 42 new tests (198 total: 156 existing untouched + 42 new).

   **Cities/Connectors/Searches tracking** (also requested in the Step 4 mission,
   beyond the original docs/16 design) are all computed on demand from already-stored
   data — `search_requests`, `platform_performance_observations`, `apartments` — with
   **no new schema or migration**: "Searches" reuses Search Memory's existing
   `search_statistics()`; "Connectors" re-groups the same platform observations
   (`connector_health()`); "Cities" aggregates over `search_observed_apartments` +
   `apartments`, keyed by the same free-text `location` string Search Memory already
   uses (`city_statistics()`/`average_city_price()`). "Most common property types" was
   deliberately not implemented — no per-apartment property-type field exists anywhere
   in the schema (V1.0 scoped to residential apartments only), so there's exactly one
   type system-wide; adding that dimension would be new schema, out of this step's
   "only accumulate evidence" scope.

   A small, zero-behavior-change fix rode along: `RawListing.status`'s default changed
   from the string `"available"` to `None`, so `availability_quality_score` can tell
   "the connector said available" apart from "the connector said nothing" — both
   reference connectors set `status` explicitly, so nothing that already worked
   changed. Full detail, including the `reliability_score` formula and why
   `ranking_usefulness_score` is excluded from it, in `docs/16_Knowledge_Engine.md`.

   Verified against the real dev database, not just tests: ran the CLI once and
   confirmed both real connectors got a genuine observation row and a
   correctly-computed `reliability_score`/`success_rate`, while platforms never
   actually searched (`zillow`, `idealista`, etc.) correctly show `NULL` rather than a
   fabricated `0`.

   **Step 4.5 — Architecture Cleanup (done, 2026-07-15).** A small, explicitly-scoped
   pass between Step 4 and Step 5, following an architecture review that found no
   blockers but five worthwhile small fixes:
   1. `storage/knowledge_repository.py` renamed to `storage/reference_data_repository.py`
      — it was colliding, by name only, with the unrelated new `src/knowledge/` package.
   2. New migration `0002_search_requests_created_at_index.sql` — adds
      `idx_search_requests_created_at`; `search_requests` had no index beyond its
      primary key despite `search_memory_repository.find_previous_search`/
      `get_search_history` scanning and sorting it by `created_at` on every completed
      search. `0001` untouched.
   3. Documented (not merged) why `history_service.previous_version()` and
      `search_memory_service._value_as_of()` both exist — see
      `docs/17_Search_Memory.md` "Two Reconstruction Helpers, Not One."
   4. Documented (not refactored, since it doesn't violate anything) why
      `analyzers/engine.py` writes to `storage/search_memory_repository.py` directly —
      see `docs/01_System_Architecture.md` "Repository Writes vs. Service Layer," the
      general rule this and the pre-existing `apartment_history_repository.add_image_event`
      direct call both already followed.
   5. One stale doc TBD resolved: `docs/03_Data_Model.md`'s `ranking_usefulness_score`
      row and Open Questions entry said "exact formula TBD" — it was implemented in
      Step 4; updated to state the actual formula instead.

   No source-code TODO/FIXME/XXX comments existed anywhere in `src/`/`tests/` to
   review — the codebase's `TBD` markers are all in `docs/` (a deliberate, different
   convention, see `docs/13_Claude_Guidelines.md`), and only the one above had actually
   been resolved by later work. 200 tests passing (198 existing + 2 new migration
   tests) — no behavior changed, only names, an index, and documentation.
5. **Connector SDK** (`BaseConnector` template method) — independent of 2–4, could be
   done in parallel; migrate `demo_platform.py`/`demo_platform_two.py` onto it as proof,
   same way Phase 7 proved the original Connector contract. **Done, 2026-07-15
   (v2.0 Step 5).** Grew well beyond the original template-method sketch into a full
   plugin framework: new `src/connectors/sdk/` package — `BaseConnector` (template
   method: `connect -> fetch_listing -> parse -> normalize -> validate ->
   ConnectorResult`), `ConnectorFactory` (the only sanctioned way to obtain a
   connector — `core/agent.py` no longer imports connector modules itself),
   `ConnectorRegistry` (self-registration via `@register_connector`, importing
   `src.connectors.<name>` on first lookup), `ConnectorMetadata`/`ConnectorCapabilities`
   (declarative coverage + capability discovery), `ConnectorConfiguration`,
   `ConnectorValidator` (structured, non-fatal-by-default field-completeness
   warnings), and a `ConnectorException` hierarchy
   (`ConnectorConnectionError`/`ParsingError`/`ValidationError`/`ConfigurationError`).
   `ConnectorHealth` was **not** redefined — it's `src.knowledge.models.ConnectorHealth`
   (Step 4), reused via `BaseConnector.health_check()`, avoiding two competing
   definitions of the same thing.

   Both reference connectors (`demo_platform`, `demo_platform_two`) were rebuilt on
   `BaseConnector` — each now implements exactly four small hooks
   (`build_url`/`parse`/`normalize`/`connector_info`) instead of one `search()` method
   that duplicated the same fetch->save->parse sequence. `core/agent.py`'s
   per-platform loop now reads `ConnectorResult.success`/`.listings`/`.response_time_ms`
   uniformly instead of measuring timing itself and catching a bare `Exception` around
   a dynamically-imported module — the old `_load_connector`/`Connector` ABC were
   removed outright (nothing needed them once the Factory existed). New
   `docs/18_Connector_SDK.md` (the mission asked for `docs/17_...`, already taken by
   Search Memory — used the next free number instead) covers architecture, lifecycle,
   how to build a new connector, best practices, and certification requirements; a
   reusable `tests/connectors/sdk/certification.py` mixin lets any connector's own test
   file certify SDK compliance for free, which both reference connectors now do.

   54 new tests (256 total: 202 existing untouched + 54 new — SDK unit tests, a
   template-method test suite using scripted fake connectors, certification tests,
   and registry/factory performance tests with hundreds of registered connectors).
   Verified against the real dev database: ran the CLI through the new
   `ConnectorFactory` -> `BaseConnector` path end-to-end and confirmed identical
   results (6 apartments from the same 2 platforms) plus correct Knowledge Engine
   observations, exactly as before the refactor.
6. **Deep Analysis Engine** (`distance.py`, `nearby.py`, `scores.py` as originally
   sketched) — originally planned last (Step 7), because it's blocked on a real
   product/vendor decision (which geocoding/transit/nearby-amenity data source) that
   still hasn't been made — see [07_Analysis_Engine.md](07_Analysis_Engine.md) Open
   Questions. **Built ahead of schedule instead, at explicit instruction, as Step 6
   (done, 2026-07-15)** — the framework (the `apartment_analysis_metrics` store,
   evidence-based analyzers) was buildable and testable with real math and curated
   fake/stubbed reference data *before* the vendor decision, exactly as this doc always
   said it could be; only real live-API metric computation still waits for that
   decision. New `src/analysis/` package: `BaseAnalyzer`/`AnalysisRegistry`
   (self-registering plugin framework, mirroring `connectors.sdk` but simpler — see
   [19_Analysis_Engine.md](19_Analysis_Engine.md) "Plugin System"), eleven analyzers
   (`walking_distance`, `public_transport`, nine "nearby X" amenity analyzers sharing
   one base class), `AnalysisPipeline`/`AnalysisEngine` (per-apartment / per-search
   orchestration), configurable composite scoring (`scoring.py` — Location/
   Convenience/Lifestyle/Accessibility/Overall, weights as data, not hardcoded),
   `analysis_service.py` (write/read persistence, append-only). `core/agent.py` now
   runs `AnalysisEngine` after Apartment History and before Ranking — the mission's own
   diagram placed it after Search Memory/Knowledge Engine too, but those two must stay
   at the very end of `run()` by their own documented design
   ([16](16_Knowledge_Engine.md)/[17](17_Search_Memory.md) "Where This Runs"); moving
   them would have broken already-passing tests, so Analysis Engine slots in as early
   as it correctly can instead. New migration `0003_analysis_engine_metrics.sql` adds
   `confidence`/`evidence_json`/`analyzer_version` to `apartment_analysis_metrics`;
   `0001`/`0002` untouched. `services/report_generator.py` gained one optional,
   backward-compatible parameter to show analyzer/composite scores, evidence, and
   warnings per listing. 58 new tests (314 total: 256 existing untouched + 58 new).

   Verified against the real dev database, not just tests: ran the CLI once with no
   curated data (zero metrics persisted — correctly honest "no evidence yet," not a
   fabricated score), then seeded a few illustrative `Example City` reference facts
   (clearly fictional demo data, same convention as `demo_platform`'s own fixtures) and
   ran again, confirming real, correctly-computed analyzer and composite scores flowed
   all the way through to the generated HTML report.
7. **First Production Connector — RentCast** (`connectors/rentcast/`) — originally the
   subject of "After v2.0: Still the Same Answer" below (deferred to *after* Version
   2.0 entirely); **reassigned to Step 7 at explicit instruction instead (done,
   2026-07-15)**. Validates the Connector SDK (Step 5) against one real, external data
   source rather than the two local fixtures it had only ever been proven against.
   Chosen source: RentCast (see "Reference Connector Strategy" above) — a real
   developer-facing REST API, `X-Api-Key` auth, a free tier, verified (not assumed)
   published Terms of Use permitting this kind of programmatic access. New
   `src/connectors/rentcast/` package: `connector.py` (`RentCastConnector`, overriding
   `connect()`/`fetch_listing()` for API-key auth and paginated HTTP calls, implementing
   `build_url`/`parse`/`normalize`/`connector_info` like every connector) and
   `client.py` (`RentCastClient` — retry/backoff transport, immediate non-retried
   failure on 401). New `src/utils/logging.py` (`get_logger`/`StructuredFormatter`) —
   the first real use of `logging` anywhere in this codebase. New migration
   `0004_production_connector_fields.sql` adds `apartments.currency`/`.property_type`
   (nullable; `0001`–`0003` untouched); `RawListing`/`Apartment`/`normalizer.py`/
   `apartment_repository.py` all gained the same two fields, plus `RawListing` gained
   `latitude`/`longitude` (already on `Apartment` since migration 0001, but never
   populated by any connector until now). Registered in
   `discovery/known_platforms.py`'s `REFERENCE_CONNECTORS` exactly like the two demo
   connectors — zero RentCast-specific code anywhere in `core/agent.py` or any
   downstream module (proven by `tests/core/test_rentcast_integration.py`).

   Also fixed along the way: a real, pre-existing bug in `BaseConnector.search()`
   (Step 5) — `connect()` was called *outside* the `try:` block, invisible until
   `RentCastConnector.connect()` became the first `connect()` override that
   legitimately needs to raise. See [20_First_Production_Connector.md](20_First_Production_Connector.md)
   "A Fix Along the Way."

   47 new tests (361 total: 314 existing untouched + 47 new — `RentCastClient`
   retry/backoff/auth-failure unit tests, `RentCastConnector` unit tests including
   malformed/sparse/missing-coordinate listings, full `search()`-level failure tests,
   SDK certification via the existing `ConnectorCertificationMixin`, and one
   full-pipeline integration test). All new tests mock the HTTP layer — no test makes a
   real network call or spends real RentCast free-tier quota. One real, live search was
   additionally run against the actual RentCast API (a real key supplied transiently,
   never logged or committed) to satisfy this step's live-verification requirement.

   Full write-up: [20_First_Production_Connector.md](20_First_Production_Connector.md)
   (numbered `20`, not the mission's requested `19` — already taken by
   [19_Analysis_Engine.md](19_Analysis_Engine.md), the same collision Steps 5/6 each
   hit and resolved the same way).
8. **Dynamic Filter Engine** — this v2.0 Step 8 slot (originally sketched as a
   `search/filters/` subpackage split, migrating the 5 existing filters plus one or
   two examples per new category) was **superseded, not built as originally
   planned**: it was built for real under **Version 2.5 Step 9** instead, as a whole
   new `src/filter_engine/` package with all ~38 mission-requested filters (not just
   one or two examples), reusing rather than migrating the 5 existing
   `search/criteria.py` definitions. See "Version 2.5" below —
   [25_Dynamic_Filter_Engine.md](25_Dynamic_Filter_Engine.md) for the full write-up.

Each step: preserve all 73 currently-passing tests, add new tests for the new behavior,
run the full suite, commit — the same discipline every phase so far has followed.

### After v2.0: Still the Same Answer

~~Once the above is built, the next real product step is unchanged from before this
upgrade: pick a real first platform and write one connector for it (now using the
Connector SDK from step 5)~~ — **resolved, and pulled forward into Version 2.0 itself
as Step 7** (RentCast, done 2026-07-15; see that step's entry above and
[20_First_Production_Connector.md](20_First_Production_Connector.md)), at explicit
instruction rather than waiting for Version 2.0 to fully complete first. The 6 originally-catalogued
candidates in `discovery/known_platforms.py` (Zillow, Apartments.com, Rightmove,
Idealista, Fotocasa, ImmoScout24) remain `connector_available = False` — none offers a
comparable self-service, ToS-compliant path — and stay available as future candidates
if a second real connector is ever wanted, following the checklist in
[20_First_Production_Connector.md](20_First_Production_Connector.md) "How to Add the
Next Connector."

## Provider Abstraction Layer (done, 2026-07-15 — not a numbered Version 2.0 step)

Requested separately, after Step 7, rather than as another numbered item in the
Implementation Order above — a distinct capability, not a continuation of any
already-planned step. Adds `src/providers/` (see
[21_Provider_Abstraction_Layer.md](21_Provider_Abstraction_Layer.md)): a common
`Provider` interface for both data providers (RentCast, local demo) and AI providers
(a local Ollama LLM, an always-available no-op), a scoring router
(`ProviderRouter`) selecting the best *available* candidate by cost/freshness/
quality, and a real fallback mechanism — a failing or unavailable provider is skipped
in favor of the next-best one, in the same run, not just at startup.

`RentalResearchAgent` gained two new, optional, default-`None` constructor parameters
(`data_router`, `ai_router`) — every existing caller is byte-identical to before this
addition. `ui/cli.py` gained one new, off-by-default flag (`--use-provider-router`).
52 new tests (413 total: 361 existing untouched + 52 new). Works with zero
configuration by design: no `RENTCAST_API_KEY` and no local Ollama running still
produces a complete search and report, via `LocalDemoDataProvider`/`NullAIProvider`.

## SDK Validation Sprint (done, 2026-07-15 — verification, not new functionality)

Requested after the Provider Abstraction Layer, to empirically check four specific
claims the Connector SDK (Step 5) has made since it was built, rather than just
re-asserting them: can a second connector be added with zero changes elsewhere; does
the factory discover it automatically; are connectors truly independent; is the
normalized model complete enough. A fourth reference connector,
`SampleJsonFeedConnector` (`src/connectors/sample_json_feed/`) — JSON, not HTML,
deliberately not seeded in `known_platforms.py` — was added purely as the controlled
experiment. All four claims held, with two genuine, honestly-reported gaps in the
normalized model (no `room_type` field; no field for a platform's own "last updated"
fact, distinct from this system's observation timestamps) and one gap found and fixed
(several already-modeled fields — currency, property type, coordinates, platform
name, listing id, description — weren't being rendered in the HTML report; now they
are). 15 new tests (428 total). Full write-up:
[22_SDK_Validation_Sprint.md](22_SDK_Validation_Sprint.md).

## Version 2.5 — Production Provider Framework (Step 8, done 2026-07-15)

Explicitly a new version, not a continuation of Version 2.0's numbered steps — begun
once the user confirmed Steps 1–7 complete, the SDK validated (docs/22), and the
architecture reviewed (docs/23). "Step 8" here is v2.5's own first step, distinct
from the Dynamic Filter Engine's "Step 8" slot in Version 2.0's own list above — that
item was subsequently built for real as **Version 2.5 Step 9** (below), not left
pending.

Completes the Provider Abstraction Layer (unnumbered Version 2.0 addition, above)
into a full production framework: `ProviderFactory`, `ProviderConfiguration`,
`ProviderHealth`, `ProviderMetrics`, `ProviderStatistics`, `ProviderValidator` — every
one either a thin wrapper over the existing Connector SDK/Knowledge Engine or new,
genuinely-needed provider-level logic (metadata range validation), never a
reimplementation. `ProviderConfiguration` closes part of a real gap the Production
Readiness Review flagged (docs/23 Q5: `rate_limit_per_minute` declared but inert) by
threading timeout/retry/credentials down into the same `ConnectorConfiguration`
mechanism a connector already understands — real enforcement of a rate limit itself
remains future work, not claimed as done here.

32 new tests (460 total: 428 existing untouched + 32 new). Full write-up:
[24_Production_Providers.md](24_Production_Providers.md).

## Version 2.5 Step 9 — Dynamic Filter Engine (done 2026-07-15)

Fulfills the Version 2.0 Step 8 slot's original intent (see that entry above) as a
new v2.5 step instead — a whole new `src/filter_engine/` package, not the originally
sketched `search/filters/` subpackage split, with all ~38 mission-requested filters
rather than one or two examples per category.

`FilterEngine`/`FilterRegistry`/`FilterFactory`/`BaseFilter`/`FilterMetadata`/
`FilterConfiguration`/`FilterResult`/`FilterValidator`/`FilterStatistics`/
`FilterHistory` — a fully modular, self-registering plugin system mirroring
`ConnectorRegistry`/`AnalysisRegistry`/`ProviderRegistry`'s established shape. 39
built-in filters: 12 genuinely data-backed (reusing `search.criteria`'s existing
`max_price`/`min_price`/`min_sqft` logic and the Deep Analysis Engine's stored
proximity scores, never duplicating either), 27 honestly dormant (real, registered,
tested filters for fields — amenities, room/flatshare preferences, structured
geography, stay duration — that don't exist anywhere in `Apartment`/`RawListing` yet;
always pass, never fabricate an exclusion, connecting directly to the "room/
flatshare" scope tension this project has deferred since v1.0). Full AND/OR/NOT/
nested composition, deterministic execution order. `search/criteria.py`'s
`get_filter()` now falls back to the new, much larger registry (a deferred import
avoiding a circular dependency), so any of the 39 filters works through
`SearchRequest.criteria` immediately, with zero changes to `SearchRequest` itself.
New migration `0005_filter_execution_history.sql` for `FilterHistory` — the one
genuinely new table this sprint needed (`0001`–`0004` untouched).

`RentalResearchAgent` gained one new, optional, default-`None` `filter_engine`
parameter (byte-identical behavior for every existing caller); `ui/cli.py` gained
one new, off-by-default `--use-filter-engine` flag. 102 new tests (562 total: 460
existing untouched + 102 new). Full write-up:
[25_Dynamic_Filter_Engine.md](25_Dynamic_Filter_Engine.md).

## Version 2.5 Step 10 — Geographic Intelligence Engine (done 2026-07-15)

A provider-independent Geographic Intelligence Engine — not a map viewer — that
calculates spatial relationships between apartments and points of interest.
`GeographicEngine`/`GeoProvider`/`GeoProviderRegistry`/`GeoProviderFactory`/`GeoCache`/
`RouteCalculator`/`DistanceCalculator`/`TravelTimeCalculator`/`NearbySearch`/
`GeoStatistics`/`GeoHistory` — a fully modular, self-registering plugin system
mirroring `ConnectorRegistry`/`AnalysisRegistry`/`ProviderRegistry`/`FilterRegistry`'s
established shape. One built-in provider, `HaversineGeoProvider`: real straight-line
distance (`src.analysis.geo.haversine_km`, reused, not reimplemented; confidence
`1.0`) plus honestly estimated walking/cycling/driving/public-transport travel time
(distance ÷ a documented, tunable average speed per mode; confidence `0.4`, lower
than the exact calculation on purpose), and nearby search across all 17 mission
categories reusing the exact `nearby_amenities`/`knowledge_entries` convention
`analysis/analyzers/nearby_amenity.py` already established (extended from that
analyzer's 9 categories to 17). `GeoCache` is the first real caching infrastructure
in this codebase — the Production Readiness Review (docs/23, Question 4) found "zero
caching infrastructure exists anywhere"; this closes that gap for real. New migration
`0006_geo_enrichment_history.sql` for `GeoHistory` (`0001`–`0005` untouched).

`RentalResearchAgent` gained one new, optional, default-`None` `geo_engine` parameter
(byte-identical behavior for every existing caller, the same `data_router`/`ai_router`/
`filter_engine` precedent); `ui/cli.py` gained one new, off-by-default
`--use-geo-engine` flag. The mission's own integration diagram placed this engine
*before* the Analysis Engine; as built, it runs after (alongside the Filter Engine)
and its output is passed directly to the report generator as an independent artifact
— never wired into `AnalysisEngine`'s or `RankingEngine.rank()`'s own scoring — the
same diagram-vs-implementation reconciliation already made explicitly for the Deep
Analysis Engine (Step 6) and the Dynamic Filter Engine (Step 9). 78 new tests (640
total: 562 existing untouched + 78 new). Full write-up:
[26_Geographic_Intelligence.md](26_Geographic_Intelligence.md).

## Version 2.5 Step 11 — Intelligent Ranking Engine V2 (done 2026-07-16)

Transforms apartment ranking from a static weighted score into a modular,
explainable, evidence-based decision engine — deterministic, no machine learning, no
opaque scoring. `RankingEngineV2`/`RankingPipeline`/`RankingRule`/`RankingRuleRegistry`/
`RankingWeights`/`RankingProfile`/`RankingEvidence`/`RankingExplanation`/
`RankingConfidence`/`RankingStatistics` — a fully modular, self-registering plugin
system mirroring `ConnectorRegistry`/`AnalysisRegistry`/`ProviderRegistry`/
`FilterRegistry`/`GeoProviderRegistry`'s established shape.

12 built-in rules, one per named input the mission's own INPUTS list requires
(Dynamic Filters, Geographic Intelligence split into Walking Distance/Public
Transport/Lifestyle, Apartment History, Knowledge Engine, Platform Reliability,
Availability, Price History, Analysis Results, Provider Health, Connector
Reliability, Search History) — none recompute a formula another engine already
owns; each reads straight from that engine's own read functions
(`knowledge_service.average_city_price()`/`platform_reliability()`/`connector_health()`,
`apartment_repository.get_price_history()`, `GeoEnrichment`, `AnalysisResult`).
Every score returns Final Score, Confidence, Evidence, Rule Contributions,
Warnings, and Timestamp, exactly as the mission requires.

The key honesty mechanism: per-apartment weight renormalization only among rules
that actually have evidence for that specific apartment — a rule with no evidence
is excluded from both the score numerator and the weight-normalization denominator,
never counted as a zero. `RankingProfile` ships two built-in presets
(`DEFAULT_PROFILE`, the mission's own worked example — Price 40%, Walking Distance
25%, Availability 15%, Public Transport 10%, Lifestyle 10% — and
`COMPREHENSIVE_PROFILE`, every rule weighted equally) plus supports any fully
custom weighting.

`RentalResearchAgent` gained one new, optional, default-`None` `ranking_engine_v2`
parameter (byte-identical behavior for every existing caller); `ui/cli.py` gained
`--use-ranking-v2` and `--ranking-profile {default,comprehensive}`. It re-scores v1
`RankingEngine`'s own survivors with a real `RankingContext`, and its output is
passed to the report generator as an independent artifact — never wired into v1
`RankingEngine`'s or `AnalysisEngine`'s own scoring, the same diagram-vs-
implementation reconciliation already made for Steps 6, 9, and 10. 94 new tests
(734 total: 640 existing untouched + 94 new). Full write-up:
[27_Intelligent_Ranking_Engine.md](27_Intelligent_Ranking_Engine.md).

## Version 2.5 Step 12 — User Feedback and Preference Learning Engine (done 2026-07-16)

A modular system that learns user preferences from explicit, traceable evidence —
deterministic, no machine learning, no opaque prediction. `FeedbackEngine`/
`FeedbackService`/`FeedbackRegistry`/`PreferenceRule` — a fully modular, self-
registering plugin system mirroring `ConnectorRegistry`/`AnalysisRegistry`/
`ProviderRegistry`/`FilterRegistry`/`GeoProviderRegistry`/`RankingRuleRegistry`'s
established shape, its 7th application. 23 built-in preference rules across 4
shared, parameterized aggregation bases (`ImportancePreferenceRule`/
`ThresholdPreferenceRule`/`CategoricalPreferenceRule`/`BooleanPreferenceRule`) —
12 real, apartment/geo-field-backed dimensions and 11 honestly dormant-field
dimensions (private bathroom, furnished, pets, ... — the same "no structured
schema field exists" situation `filter_engine`'s 27 dormant filters already
documented for the identical fields), each learning only from explicit filter
choices for the latter group.

New migration `0007_feedback_and_preferences.sql` — `feedback_events` (genuinely
append-only, no `update_*`/`delete_*` function anywhere), `preference_observations`,
`preference_adjustments` (the source of truth for "current" preference values —
undo/reset write new rows that move the evidence cutoff forward, never deleting a
raw event), `preference_snapshots`. Centralized decay/confidence math
(`src/feedback/decay.py`) implements every "Learning Rules" requirement the
mission names: a single action can't strongly alter the profile, conflicting
behavior reduces confidence, explicit observations count `3×` more than inferred
ones, and the decay half-life is a configurable `DecayConfig`, not a hidden
constant.

`src/feedback/ranking_adapter.py` is the *only* module coupling `feedback` to
`ranking_v2` — three modes (`EXPLICIT_ONLY`/`SUGGESTED`/`ASSISTED`), the first two
leaving the caller's `RankingProfile` completely untouched, only `ASSISTED`
substituting a learned profile seeded from the user's own explicit weights.
`RentalResearchAgent` gained three new, optional, default-`None`/`SUGGESTED`
parameters (`feedback_engine`/`feedback_profile_id`/`feedback_mode`), byte-
identical behavior for every existing caller; a new, separate
`src/ui/feedback_cli.py` entry point (kept apart from `ui/cli.py`'s own search
command to preserve its backward compatibility) exposes
record/profile/explain/history/undo/reset/export subcommands. 130 new tests (864
total: 734 existing untouched + 130 new), including a structural privacy
guardrail test asserting every registered preference dimension's key/description/
category contains no sensitive-trait terminology. Full write-up:
[28_User_Feedback_and_Preference_Learning.md](28_User_Feedback_and_Preference_Learning.md).

## Version 2.5 Step 13 — Automatic Platform Discovery Agent (done 2026-07-16)

A provider-independent system that discovers, evaluates, deduplicates, classifies,
verifies, and stores rental-platform *candidates* for a requested country/region/
city/language/rental-category — explicitly **not** connector generation, and
explicitly **not** bypassing authentication/CAPTCHAs/robots restrictions/rate
limits. `src/discovery/automatic/` — `AutomaticDiscoveryAgent`/`DiscoveryProviderRegistry`/
`DiscoveryProvider`, an 8th application of this codebase's established self-
registering plugin shape (`ConnectorRegistry`/`AnalysisRegistry`/`ProviderRegistry`/
`FilterRegistry`/`GeoProviderRegistry`/`RankingRuleRegistry`/`FeedbackRegistry`).
Two built-in providers ship this sprint (`curated_seed` — surfaces
`discovery/known_platforms.py`'s existing public facts; `manual_url` — surfaces a
request's own `manual_urls`); adding a third requires zero `AutomaticDiscoveryAgent`
changes.

The Existing Platform Registry (`discovery/platform_registry.py`) is checked *first*,
every run, and remains the sole canonical, active registry — this agent only ever
contributes *candidates*; promotion to a real `platforms` row happens exclusively
through the existing `DiscoveryAgent.sync_platforms()` path, via a new
`discovery-cli approve-candidate`/`reject-candidate` pair, never automatically. New
migration `0008_automatic_platform_discovery.sql` — 7 tables (`discovery_runs`,
`platform_candidates`, `platform_evidence`, `platform_verification_observations`,
`platform_capability_estimates`, `platform_duplicate_links`,
`discovery_provider_observations`); every table but `discovery_runs`/
`platform_candidates` is strictly append-only, mirroring migration 0007's own
append-only-except-current-state-row shape.

Classification (13 categories) is deterministic keyword scoring, never opaque ML.
Verification/capability estimation reuse a single injectable `PageFetcher` (real
`HttpPageFetcher` in production, a fixture in every test — "do not use uncontrolled
scraping in tests," the mission's own words) so no test ever makes a real network
call. Connector availability is cross-checked honestly via the existing
`ConnectorRegistry` — never invented. 78 new tests (942 total: 864 existing
untouched + 78 new). Full write-up:
[29_Automatic_Platform_Discovery.md](29_Automatic_Platform_Discovery.md).

## Beyond Version 2.0 (explicitly deferred)

Renamed from "V2+" to avoid confusion with the new, formal "Version 2.0" above — this
section always meant "later than whatever's current," not literally "version 2." None of
the items below are addressed by Version 2.0; they're still all genuinely future:

- Cross-platform apartment de-duplication/merging (`apartments.merged_into_id` — see [07_Analysis_Engine.md](07_Analysis_Engine.md))
- AI-assisted ranking explanations / report summaries (`src/ai/` reserved, see [02_Folder_Guide.md](02_Folder_Guide.md))
- Additional rental types beyond residential apartments
- A web UI (V1 is CLI-only)
- Structured (CSV/JSON) report export alongside HTML
