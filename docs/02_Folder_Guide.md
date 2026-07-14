# 02 — Folder Guide

Status: V1.0 package structure confirmed (2026-07-14), including resolution of the legacy-folder reconciliation that had been deliberately deferred since 2026-07-13 (see [../learning/architecture_notes.md](../learning/architecture_notes.md)).

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
    base.py                      # Connector contract (abstract base / protocol)
    README.md                     # already exists — orientation + link to 06_Connector_Framework.md
    # one file per platform, e.g. example_platform.py — none yet
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
  ranking/
    __init__.py
    ranking_engine.py                     # see 08_Ranking_System.md
    scoring.py                             # weighted-sum scoring functions
  storage/
    __init__.py
    database.py                             # SQLite connection/session management
    schema.sql                               # DDL for all tables in 03_Data_Model.md
    migrations/
      0001_initial.sql
    apartment_repository.py                   # CRUD + history writes for apartments
    search_repository.py                       # search_requests / search_results
    knowledge_repository.py                      # knowledge_entries
  services/
    __init__.py
    report_generator.py                           # HTML Report Generator — see 09_Report_System.md
    report_templates/                              # Jinja2-style templates
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
| `src/browser/browser_manager.py` | Move into `src/collectors/browser_collector.py`, expanded from a test function into a reusable class | Belongs in the new Collector abstraction |
| `src/config/config_loader.py` | Move into `src/core/config.py` | One config loader, one location |
| `src/models/configuration.py` | Delete (duplicate of the above) | Was an accidental parallel to `config/config_loader.py` |
| `src/model/apartment.py` | Move into `src/storage/` as the `Apartment` dataclass backing the schema in [03_Data_Model.md](03_Data_Model.md) | Data model belongs next to the repository code that persists it |
| `src/data_source/` | Delete (empty) | Superseded by `connectors/` + `collectors/` |
| `src/filters/` | Delete (empty) | Superseded by `search/criteria.py` |
| `src/exporters/`, `src/reports/` | Delete (empty) | Superseded by `services/report_generator.py` |
| `src/maps/` | Delete (empty) | Geocoding/location logic folds into `analyzers/enricher.py` for V1 — not enough scope yet for its own module |
| `src/ai/` | Keep, empty, reserved | Not part of V1.0 scope (see Non-Goals in [00_Project_Vision.md](00_Project_Vision.md)) — reserved for V2 AI-assisted ranking explanations/report summaries so the folder doesn't need to be re-created later |

This reconciliation is a `src/` restructuring task, not a docs task — execute it when implementation begins (see [10_Roadmap.md](10_Roadmap.md) Phase 1), not as part of this architecture pass.

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
