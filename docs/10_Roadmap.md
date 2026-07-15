# 10 — Roadmap

Status: **V1.0 (7 phases) + v1.1 (Multi-Platform Discovery Framework) live in code and tested, as of 2026-07-14.** Version 2.0 is fully designed; **Implementation Steps 1–6 are done** — Migration Framework (Sprint V2.0.1), Apartment History Engine (Step 2), Search Memory & Comparison Engine (Step 3), the Knowledge Engine (Step 4), an architecture cleanup pass (Step 4.5), the Connector SDK & Plugin Framework (Step 5), and the Deep Analysis Engine (Step 6, 314 tests passing). **Step 6 was built ahead of Step 7** (Dynamic Filter Engine) at explicit instruction, swapping the original plan's order — the numbered list below now reflects the order things actually happened in, not the original sequencing; see that step's entry for the reasoning. Step 7 remains designed but not implemented. See "Version 2.0" below. Update this as priorities shift — it should always reflect current reality, not the original plan.

## Reference Connector Strategy

No real rental platform had been chosen when Phases 3–7 were built (the "which platform first" question in [../notes/Questions.md](../notes/Questions.md) was still open). Rather than block architecture completion on that product decision, or unilaterally pick a real commercial site to scrape without confirming its ToS, every phase from here on was proven against **`demo_platform`** and **`demo_platform_two`** — real `Connector` implementations that fetch real local HTML fixtures via a real Playwright browser and parse them with BeautifulSoup, exactly like a connector for a live site would, but touching no external service. This is explicitly not a shortcut around the exit criteria — every fetch, parse, database write, and report generation described below is real; only the *source* is a controlled fixture instead of a commercial website. Swapping in a real platform means writing one more connector implementing the same contract (see [06_Connector_Framework.md](06_Connector_Framework.md)) — nothing else changes, which Phase 7 exists specifically to demonstrate.

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
   populates coordinates yet (Step 7) and "removed" requires Search Memory's
   full-observed-set comparison (Step 3) to mean what the mission intends rather than
   "excluded by this run's filters." Full writeup in `learning/architecture_notes.md`.
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
7. **Dynamic Filter Engine** (`search/filters/` subpackage split) — independent of 2–6;
   migrate the 5 existing filters first (behavior-preserving refactor), then add one or
   two real filters per new category as *examples* of the pattern working, not all ~25
   at once — the framework, not the exhaustive filter list, is what v2.0 is scoped to.
   Now unblocked to actually read real `apartment_analysis_metrics` data for its
   proximity/score filters, since Step 6 made that data genuinely producible.

Each step: preserve all 73 currently-passing tests, add new tests for the new behavior,
run the full suite, commit — the same discipline every phase so far has followed.

### After v2.0: Still the Same Answer

Once the above is built, the next real product step is unchanged from before this
upgrade: **pick a real first platform and write one connector for it** (now using the
Connector SDK from step 5), following the pattern `demo_platform.py`/`demo_platform_two.py`
already established. The 6 candidates in `discovery/known_platforms.py` are still
sitting ready, `connector_available = False`, in [notes/Questions.md](../notes/Questions.md).

## Beyond Version 2.0 (explicitly deferred)

Renamed from "V2+" to avoid confusion with the new, formal "Version 2.0" above — this
section always meant "later than whatever's current," not literally "version 2." None of
the items below are addressed by Version 2.0; they're still all genuinely future:

- Cross-platform apartment de-duplication/merging (`apartments.merged_into_id` — see [07_Analysis_Engine.md](07_Analysis_Engine.md))
- Automated platform discovery (see [05_Platform_Discovery.md](05_Platform_Discovery.md))
- AI-assisted ranking explanations / report summaries (`src/ai/` reserved, see [02_Folder_Guide.md](02_Folder_Guide.md))
- Additional rental types beyond residential apartments
- A web UI (V1 is CLI-only)
- Structured (CSV/JSON) report export alongside HTML
