# 10 — Roadmap

Status: **All 7 V1.0 phases complete, plus Version 1.1 (Multi-Platform Discovery Framework), as of 2026-07-14.** The full pipeline runs end-to-end against real reference connectors, and the platform registry now tracks 8 real-world platform candidates (2 usable, 6 catalogued for future connectors). See "Reference Connector Strategy" and "Version 1.1" below. Update this as priorities shift — it should always reflect current reality, not the original plan.

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

## What's Next

Still not architectural: **pick a real first platform and write one connector for it**,
following the exact pattern `demo_platform.py`/`demo_platform_two.py` already established.
v1.1 narrows this from an open-ended question to a concrete shortlist — the 6 platforms in
`discovery/known_platforms.py` are sitting in the registry as `connector_available = False`,
ready for whichever one gets picked first.

## V2+ (explicitly deferred, not in V1.0)

- Cross-platform apartment de-duplication/merging (`apartments.merged_into_id` — see [07_Analysis_Engine.md](07_Analysis_Engine.md))
- Automated platform discovery (see [05_Platform_Discovery.md](05_Platform_Discovery.md))
- AI-assisted ranking explanations / report summaries (`src/ai/` reserved, see [02_Folder_Guide.md](02_Folder_Guide.md))
- Additional rental types beyond residential apartments
- A web UI (V1 is CLI-only)
- Structured (CSV/JSON) report export alongside HTML
