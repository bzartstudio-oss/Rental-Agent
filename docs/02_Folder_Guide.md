# 02 — Folder Guide

Status: V1.0 package structure **built and tested, not just planned** (2026-07-14) — every file below exists and is exercised by the test suite (56 tests, see [10_Roadmap.md](10_Roadmap.md)), including resolution of the legacy-folder reconciliation that had been deliberately deferred since 2026-07-13 (see [../learning/architecture_notes.md](../learning/architecture_notes.md)).

## Top-level folders

| Folder | Purpose | What belongs here | What doesn't |
|---|---|---|---|
| `learning/` | Running project journal, split by topic | `python_notes.md`, `git_notes.md`, `architecture_notes.md`, `playwright_notes.md`, `database_notes.md`, indexed from `Project Learning.md` | Formal architecture docs (`docs/`), raw platform research (`notes/`) |
| `docs/` | Project documentation — the numbered files in this folder | Architecture, data model, roadmap, glossary, journal | Code, prompts, raw data |
| `notes/` | Raw research on rental platforms and the rental market | Site structure/auth/rate-limit findings, market observations | Curated lessons (`learning/`), formal docs (`docs/`) |
| `prompts/` | Prompt templates used by the agent at runtime | Versioned `.txt`/`.md` prompt files referenced from `src/` | One-off exploratory prompts |
| `src/` | Source code — see package structure below | Application code | Notes, data, generated output |
| `data/` | Persistent data | `rental_intelligence.db` (the database — see [03_Data_Model.md](03_Data_Model.md)), plus file-based stores below | Anything the agent generates as a *deliverable* (that's `output/`) |
| `output/` | Generated deliverables | HTML reports produced by a run | Anything checked in as a fixed input |
| `images/` | Doc-support image assets | Screenshots/diagrams referenced *from docs* | Listing photos (those go in `data/media/`) |
| `tests/` | Test suite | Mirrors `src/` structure 1:1 | — |

## `data/` subfolders

Revised now that SQLite is the system of record for structured data (see [03_Data_Model.md](03_Data_Model.md)) — `apartments/`, `search_history/`, and `platform_registry/` as originally scaffolded on 2026-07-13 are now superseded by database tables and kept only as legacy/empty unless repurposed:

| Subfolder | Purpose | Status |
|---|---|---|
| `knowledge_base/` | Hand-authored source material later loaded into the `knowledge_entries` table | Active |
| `media/` | Downloaded listing images, referenced by `apartment_images.local_path` | Active |
| `raw_pages/` | Unprocessed HTML/screenshots per fetch, referenced by `raw_captures.raw_page_path` | Active |
| `cache/` | Short-lived, safe-to-delete request cache | Active |
| `platform_registry/`, `apartments/`, `search_history/` | Pre-SQLite scaffolding | Superseded — leave empty, do not write new code against these; revisit deletion once `storage/` is implemented and nothing references them |

## `src/` package structure (V1.0)

```
src/
  core/
    __init__.py
    agent.py                 # RentalResearchAgent — the orchestrator (see 01_System_Architecture.md)
    config.py                # app-wide configuration loading
  search/
    __init__.py
    search_request.py        # SearchRequest — see 04_Search_Request.md
    criteria.py               # filter/criteria registry
  discovery/
    __init__.py
    discovery_agent.py         # DiscoveryAgent — see 05_Platform_Discovery.md
    platform_registry.py         # reads/writes the `platforms` table
  connectors/
    __init__.py
    base.py                      # Connector contract (RawListing, Connector ABC)
    README.md                     # orientation + link to 06_Connector_Framework.md
    demo_platform.py               # reference/demo connector — not a real platform, see 10_Roadmap.md
    demo_platform_two.py            # second reference connector, different fixture shape (Phase 7)
    fixtures/
      demo_platform/listings.html, images/
      demo_platform_two/listings.html, images/
  collectors/
    __init__.py
    browser_collector.py           # Playwright-based fetch — absorbs src/browser/browser_manager.py
    http_collector.py               # plain HTTP fetch, for platforms with a usable API
    image_collector.py               # downloads listing images into data/media/
    raw_page_store.py                 # persists raw HTML/screenshots into data/raw_pages/
  analyzers/
    __init__.py
    normalizer.py                     # RawListing -> Apartment shape
    deduplicator.py                    # within-platform duplicate detection (V1); cross-platform is V2
    enricher.py                         # derived fields, consults knowledge_entries
    change_detector.py                   # decides when to write new price/availability history rows
    engine.py                             # composes the four above into the write sequence (07_Analysis_Engine.md) — added during implementation, not in the original plan; core/agent.py must not contain per-listing business logic, so that composition needed a home in analyzers/
  ranking/
    __init__.py
    ranking_engine.py                     # see 08_Ranking_System.md
    scoring.py                             # weighted-sum scoring functions
  storage/
    __init__.py
    database.py                             # SQLite connection/session management
    schema.sql                               # DDL for all tables in 03_Data_Model.md
    models.py                                 # dataclasses mirroring each table
    apartment_repository.py                   # CRUD + history writes for apartments
    search_repository.py                       # search_requests / search_results
    knowledge_repository.py                      # knowledge_entries
  services/
    __init__.py
    report_generator.py                           # HTML Report Generator — see 09_Report_System.md. Plain Python string templating, not Jinja2 (not an installed dependency, not needed for V1's layout)
  ui/
    __init__.py
    cli.py                                          # V1 entry point — the only place a human interacts with the system
  utils/
    __init__.py
    logging.py
    ids.py                                            # UUID generation for apartments/search_requests
  rental_agent.py                                       # thin script wrapper: parses argv, calls ui.cli
```

## Legacy folder reconciliation (resolves the item deferred on 2026-07-13)

| Legacy path | Disposition | Reason |
|---|---|---|
| Legacy path | Disposition | Status |
|---|---|---|
| `src/browser/browser_manager.py` | Moved into `src/collectors/browser_collector.py`, expanded from a one-off test function into a reusable `BrowserCollector` context-manager class | **Done** (2026-07-14) |
| `config/settings.json`, `src/config/config_loader.py`, `src/model/apartment.py`, `src/models/configuration.py` | Deleted, not migrated — confirmed stale/experimental by the user (2026-07-14): modeled a different, narrower concept (flatshare room search in Valencia via specific platforms) that doesn't reflect the confirmed V1.0 design. `src/storage/models.py` defines a fresh `Apartment` dataclass from [03_Data_Model.md](03_Data_Model.md) instead; `src/core/config.py` is a fresh, minimal app-config module (paths + `.env` loading), not a revival of the old per-search `Configuration` schema. See [../learning/architecture_notes.md](../learning/architecture_notes.md). | **Done** (2026-07-14) |
| `main.py` (project root) | Deleted — only ever exercised the deleted `config_loader`/prototype code, and wasn't part of the documented structure (the real V1 entry point is `src/rental_agent.py`, see below) | **Done** (2026-07-14) |
| `src/data_source/`, `src/filters/`, `src/exporters/`, `src/reports/`, `src/maps/` | Deleted (all were empty) — superseded by `connectors/`+`collectors/`, `search/criteria.py`, `services/report_generator.py`, and `analyzers/enricher.py` respectively | **Done** (2026-07-14) |
| `src/ai/` | Kept, empty, reserved | Not part of V1.0 scope (confirmed 2026-07-14, see Non-Goals in [00_Project_Vision.md](00_Project_Vision.md)) — reserved for V2 AI-assisted ranking explanations/report summaries |

This table is a historical record of the reconciliation now that it's done — see [../learning/architecture_notes.md](../learning/architecture_notes.md) for the full reasoning behind each disposition.

## Root files

| File | Purpose |
|---|---|
| `README.md` | Quick orientation + setup instructions for a new clone |
| `CLAUDE.md` | Working agreement for how Claude should operate in this project |
| `requirements.txt` | Python dependencies |
| `.env` | Local secrets/config (gitignored, never committed) |
| `.gitignore` | Excludes `.env`, `.venv/`, `__pycache__/`, generated `output/` contents |

## Related Documents

- [01_System_Architecture.md](01_System_Architecture.md)
