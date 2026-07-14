# 10 — Roadmap

Status: **V1.0 (7 phases) + v1.1 (Multi-Platform Discovery Framework) live in code and tested (73 tests), as of 2026-07-14.** The full pipeline runs end-to-end against real reference connectors, and the platform registry tracks 8 real-world platform candidates (2 usable, 6 catalogued). **Version 2.0 (Autonomous Rental Intelligence Platform — Knowledge Engine, Apartment History, Search Memory, Platform Intelligence, Dynamic Filter Engine, Deep Analysis Engine, Connector SDK, Agent Architecture) is fully designed as of 2026-07-14 but explicitly not yet implemented** — see "Version 2.0" below for the migration plan and implementation order. Update this as priorities shift — it should always reflect current reality, not the original plan.

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

### Migration Plan

**This is the first schema change that gets a real migrations mechanism**, rather than
another "delete the dev database and let it regenerate" (what v1.1 did — acceptable
there because the changed columns had no real data yet; not acceptable going forward,
per "must NEVER lose information from previous searches" and "assume hundreds of
thousands of records").

1. **Add `storage/migrations/`** — numbered SQL files, plus a new `schema_migrations`
   table (`version INTEGER PK`, `applied_at TEXT`) that tracks which have run.
   `storage/database.py`'s schema application step changes from "run `schema.sql`" to
   "run `schema.sql` (still safe/idempotent for brand-new tables via `CREATE TABLE IF
   NOT EXISTS`), then run any migration file whose version isn't in
   `schema_migrations` yet, each inside its own transaction, recording success before
   moving to the next."
2. **`0001_v2_knowledge_engine.sql`** — the entire v2.0 change set in one migration:
   - 6 new tables via `CREATE TABLE IF NOT EXISTS` (safe either way, tracked for audit
     consistency): `apartment_change_log`, `apartment_image_events`,
     `platform_performance_observations`, `filter_definitions`,
     `apartment_analysis_metrics`, `search_observed_apartments`.
   - `ALTER TABLE ADD COLUMN` for every new column on existing tables — all nullable or
     defaulted, so existing rows need no backfill: `platforms` (+7 columns),
     `apartments` (+1: `description`), `apartment_images` (+2: `thumbnail_path`,
     `is_current` default `1`), `search_requests` (+8).
3. **Why this one is backward-compatible and the v1.1 one wasn't:** v1.1 dropped/renamed
   columns (`base_url` → `homepage`/`search_url`, `is_active` removed) — genuinely
   incompatible with old rows, hence the reset. v2.0 only *adds* nullable columns and new
   tables — old code paths that don't know about them keep working unmodified, and this
   migration can run against a database that already has real accumulated data. No dev-db
   reset needed this time.
4. **Code changes that ride along with the migration** (not part of the SQL, but must
   ship in the same commit so the schema and the code that reads/writes it never
   diverge): `storage/models.py`'s `Platform`/`Apartment`/`ApartmentImage`/
   `SearchRequestRecord` dataclasses gain the new fields; every repository function that
   does `SELECT *` and maps to a dataclass needs the new columns added to its mapping.

### Implementation Order

Sequenced by dependency, not by requirement number — schema first, then whatever's
self-contained, ending with the one piece that has an unresolved external dependency:

1. **Migrations framework + v2.0 schema** (above) — everything else depends on it existing first.
2. **Apartment History extensions** (`apartment_change_log`, `apartment_image_events`) —
   a direct, self-contained extension of the existing, working `analyzers/change_detector.py`
   and `analyzers/engine.py` write sequence. Low risk, high value, do it early.
3. **Search Memory** (`search_observed_apartments`, `search_requests` run-stats columns,
   run-over-run comparison) — needed before Knowledge Engine, since Knowledge Engine
   observations are keyed by `search_id` and conceptually "when did this search finish."
4. **Knowledge Engine + Platform Intelligence rollups** — depends on Search Memory's
   `search_id`/timing being solid; this is the "self-improving" mechanism, worth landing
   before more platforms/connectors get added so every connector built afterward is
   automatically tracked from its first run.
5. **Connector SDK** (`BaseConnector` template method) — independent of 2–4, could be
   done in parallel; migrate `demo_platform.py`/`demo_platform_two.py` onto it as proof,
   same way Phase 7 proved the original Connector contract.
6. **Dynamic Filter Engine** (`search/filters/` subpackage split) — independent of 2–5;
   migrate the 5 existing filters first (behavior-preserving refactor), then add one or
   two real filters per new category as *examples* of the pattern working, not all ~25
   at once — the framework, not the exhaustive filter list, is what v2.0 is scoped to.
7. **Deep Analysis Engine** (`distance.py`, `nearby.py`, `scores.py`) — last, because it's
   blocked on a real product/vendor decision (which geocoding/transit/nearby-amenity data
   source) that hasn't been made — see [07_Analysis_Engine.md](07_Analysis_Engine.md)
   Open Questions. Framework (the `apartment_analysis_metrics` store, the
   `SearchRequest` → proximity-filter plumbing) can be built and tested with fake/stubbed
   metrics before that decision is made; real metric computation waits for it.

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
