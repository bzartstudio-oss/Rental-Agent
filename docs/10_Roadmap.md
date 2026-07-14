# 10 — Roadmap

Status: V1.0 phased plan confirmed (2026-07-14). Update this as phases complete or priorities shift — it should always reflect current reality, not the original plan.

## Why This Order

Storage comes first, before any pipeline logic, because every other module either writes to it or reads from it — building connectors or ranking against a schema that doesn't exist yet would mean building twice. The first connector comes before a second one on purpose too: Phase 4 exists specifically to prove the Connector/Collector abstraction against one real, messy website before investing in a second, so any abstraction mistakes get fixed once instead of twice.

## Phase 0 — Foundations (done)

Repo scaffolded, working agreement established, documentation structure in place (this doc set), Python environment + Playwright/Chromium installed, rental type and `data/` layout decided.

## Phase 1 — Storage Foundation

- `storage/schema.sql` implementing every table in [03_Data_Model.md](03_Data_Model.md)
- `storage/database.py` connection management
- `storage/apartment_repository.py`, `search_repository.py`, `knowledge_repository.py`
- Execute the legacy-folder reconciliation in [02_Folder_Guide.md](02_Folder_Guide.md) (move `browser_manager.py` → `collectors/`, `config_loader.py` → `core/config.py`, `apartment.py` → `storage/`, delete the empty superseded folders)
- Exit criteria: can insert/read a hand-crafted `Apartment` row and its history, round-trip, from a test — no connector needed yet

## Phase 2 — Platform Registry + Discovery Agent

- `discovery/platform_registry.py`, `discovery/discovery_agent.py`
- One seed platform row (even before its connector exists) so later phases have something to reference
- Exit criteria: `DiscoveryAgent.discover(request)` returns that seed platform

## Phase 3 — Collectors

- `collectors/browser_collector.py` (the promoted `browser_manager.py`), `collectors/raw_page_store.py`, `collectors/image_collector.py`
- Exit criteria: can fetch and persist a real page from the seed platform into `data/raw_pages/`, independent of any connector-level parsing yet

## Phase 4 — First Connector, End-to-End

- One real connector for the seed platform, implementing the contract in [06_Connector_Framework.md](06_Connector_Framework.md)
- `search/search_request.py` + a minimal `search/criteria.py` registry (enough fields to run one real search)
- `analyzers/normalizer.py` + `deduplicator.py` + `change_detector.py` (enrichment can wait for Phase 5)
- Exit criteria: one real `SearchRequest` → real listings → rows in `apartments`/`apartment_price_history`/`apartment_availability_history`/`apartment_images`. This is the first point the whole pipeline shape from [01_System_Architecture.md](01_System_Architecture.md) is actually proven, not just designed.

## Phase 5 — Ranking + Reports

- `ranking/ranking_engine.py`, `ranking/scoring.py`
- `services/report_generator.py` + templates
- `search_repository` writes for `search_requests`/`search_results` (making Phase 4's runs properly reproducible per Principle 4, not just stored)
- `ui/cli.py` ties it all together as one runnable command
- Exit criteria: running the CLI end-to-end produces `output/<search_id>.html` with real data, images, URLs, and score breakdowns

## Phase 6 — Re-run & Compare

- Run the same `SearchRequest` again against the same platform after some real time has passed
- Exit criteria: `apartment_price_history`/`apartment_availability_history` show real second entries where prices/status actually changed, and nothing was overwritten — this is the first real validation of Principles 1, 3, and 4, not just a schema that supports them in theory

## Phase 7 — Second Connector

- A second, different platform, implementing the same contract
- Exit criteria: added with zero changes to `analyzers/`, `ranking/`, `storage/`, or `services/` — if anything outside `connectors/`/`discovery/` needed to change, that's a signal the Principle 7 boundary leaked somewhere in Phases 1–5 and needs fixing before a third platform makes it worse

## V2+ (explicitly deferred, not in V1.0)

- Cross-platform apartment de-duplication/merging (`apartments.merged_into_id` — see [07_Analysis_Engine.md](07_Analysis_Engine.md))
- Automated platform discovery (see [05_Platform_Discovery.md](05_Platform_Discovery.md))
- AI-assisted ranking explanations / report summaries (`src/ai/` reserved, see [02_Folder_Guide.md](02_Folder_Guide.md))
- Additional rental types beyond residential apartments
- A web UI (V1 is CLI-only)
- Structured (CSV/JSON) report export alongside HTML
