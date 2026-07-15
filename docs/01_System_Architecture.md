# 01 — System Architecture

Status: V1.0/v1.1 pipeline live in code. **v2.0 (Knowledge Engine feedback loop,
Search Memory, Deep Analysis Engine) designed 2026-07-14, not yet implemented** — see
"The v2.0 Feedback Loop" below. This is the map of the whole system — read this first,
then follow the links into the doc that owns the detail for each component.

## Orchestrator: the Rental Research Agent

`RentalResearchAgent` (`src/core/agent.py`) is the single entry point that runs a full search end-to-end. It does not itself contain business logic for any stage — it owns *sequencing*: call Discovery, hand results to Connectors, hand raw output to Analysis, hand normalized apartments to Ranking, persist the run to Search History, hand the ranked list to the Report Generator. Every stage below is independently testable without the orchestrator; the orchestrator's only job is coordination and error isolation (one connector failing shouldn't abort the whole run — see [06_Connector_Framework.md](06_Connector_Framework.md)).

## Pipeline & Data Flow

```
 ConfigurableSearchRequest                                                    (search/)
           │
           ▼
   ┌───────────────┐
   │ Discovery Agent │──reads──▶ Platform Registry ◀──storage──── data/platform_registry/
   └───────┬───────┘                                                          (discovery/)
           │ list[Platform]
           ▼
   ┌───────────────┐        ┌─────────────┐
   │  Connectors     │──uses──▶│ Collectors   │──writes──▶ data/raw_pages/, data/media/
   │ (per-platform)  │        │ (fetch/image)│                                (connectors/, collectors/)
   └───────┬───────┘        └─────────────┘
           │ list[RawListing]
           ▼
   ┌───────────────┐
   │ Analysis Engine │◀──reads──── Knowledge Database (data/knowledge_base/)
   │ normalize │      │
   │ dedupe    │      │──writes price/availability history, not just current state
   │ enrich    │      │                                                        (analyzers/)
   └───────┬───────┘
           │ list[Apartment] (current view, this run)
           ▼
   ┌───────────────┐
   │ Apartment Database │◀────────────────────────────────────────────────  (storage/)
   │ (SQLite, versioned) │                                     data/rental_intelligence.db
   └───────┬───────┘
           │
           ▼
   ┌───────────────┐
   │ Ranking Engine   │                                                       (ranking/)
   └───────┬───────┘
           │ list[RankedApartment]
           ▼
   ┌───────────────┐
   │ Search History DB │  (immutable snapshot of this run — see 03_Data_Model.md)  (storage/)
   └───────┬───────┘
           ▼
   ┌───────────────┐
   │ HTML Report Generator │──writes──▶ output/*.html                          (services/)
   └───────┬───────┘
           ▼
   ┌───────────────┐
   │ Knowledge Engine │──writes──▶ platform_performance_observations ──rolls up──▶ platforms
   └───────────────┘                                                             (knowledge/)
```

## The v2.0 Feedback Loop

Everything above the `HTML Report Generator` box is v1.0/v1.1, live, unchanged in shape.
v2.0 adds one new terminal step: after a run completes, the **Knowledge Engine**
([16_Knowledge_Engine.md](16_Knowledge_Engine.md)) records what happened (which platforms
worked, how well) as permanent observations, which roll up into the `platforms` table's
Platform Intelligence columns ([05_Platform_Discovery.md](05_Platform_Discovery.md)).
This is the literal mechanism behind "self-improving through accumulated knowledge"
([00_Project_Vision.md](00_Project_Vision.md) Mission) — the *next* search's Discovery
Agent reads a `platforms` table that already reflects everything learned from every prior
search, without any code having changed. Two other v2.0 additions thread through the
existing boxes rather than adding new ones: the Analysis Engine box now also runs the
**Deep Analysis Engine** ([07_Analysis_Engine.md](07_Analysis_Engine.md)) and writes
**Search Memory** ([17_Search_Memory.md](17_Search_Memory.md)) comparison data; the
Ranking Engine box now consults the **Dynamic Filter Engine**
([04_Search_Request.md](04_Search_Request.md)).

## Module Responsibility Table

| Module (package) | Responsibility | Must NOT contain | Doc |
|---|---|---|---|
| `core/` | Orchestration (`RentalResearchAgent`), app configuration | Any single stage's business logic | this doc |
| `search/` | Define, validate, and extend `SearchRequest` criteria | Platform-specific logic, ranking logic | [04_Search_Request.md](04_Search_Request.md) |
| `discovery/` | Decide which platforms apply to a request; own the Platform Registry | Fetching/parsing listing data | [05_Platform_Discovery.md](05_Platform_Discovery.md) |
| `connectors/` | Platform-specific query logic: criteria → raw listing data for exactly one platform, via `sdk/`'s `BaseConnector` | Normalization, ranking, storage, any *other* platform's logic | [06_Connector_Framework.md](06_Connector_Framework.md) |
| `connectors/sdk/` **(v2.0 Step 5, live)** | The Connector SDK & Plugin Framework: `BaseConnector` template method, `ConnectorFactory`/`ConnectorRegistry`, structured errors/validation/metadata | Any platform-specific logic itself — this package is the framework every connector uses, not a connector | [18_Connector_SDK.md](18_Connector_SDK.md) |
| `connectors/rentcast/` **(v2.0 Step 7, live)** | The first production (real, non-demo) connector — a real REST API, `X-Api-Key` auth, retry/backoff transport | Any SDK-level logic (that stays in `connectors/sdk/`), any non-RentCast platform logic | [20_First_Production_Connector.md](20_First_Production_Connector.md) |
| `collectors/` | Generic fetch infrastructure (browser/HTTP), image download, raw-page persistence — shared by all connectors | Platform-specific parsing/selectors | [06_Connector_Framework.md](06_Connector_Framework.md) |
| `analyzers/` | Normalize raw listings into `Apartment` records, de-duplicate, enrich, detect price/availability changes | Platform-specific field mapping (that's the connector's job to hand over already-shaped `RawListing` data) | [07_Analysis_Engine.md](07_Analysis_Engine.md) |
| `history/` **(v2.0 Step 2, live)** | Turn a normalized observation into structured `Change` objects and append them to `apartment_change_log`; reconstruct timelines/prior versions for reading | Deciding *when* it's called (that's `analyzers/engine.py`), downloading images (that stays `analyzers/`+`collectors/`) | [07_Analysis_Engine.md](07_Analysis_Engine.md) |
| `search_memory/` **(v2.0 Step 3, live)** | Record a completed search's full execution stats and run-over-run comparison; reconstruct history/timelines/statistics for reading | Deciding *when* to call it (that's `core/agent.py`), any AI/predictive logic (explicitly out of scope) | [17_Search_Memory.md](17_Search_Memory.md) |
| `knowledge/` **(v2.0 Step 4, live)** | Record per-search platform performance observations; recompute Platform Intelligence rollups; summarize accumulated evidence (platforms/connectors/cities) for reading | Any AI, prediction, or automatic decision-making (explicitly out of scope) — knowledge only ever grows, application code doesn't | [16_Knowledge_Engine.md](16_Knowledge_Engine.md) |
| `analysis/` **(v2.0 Step 6, live)** | Enrich already-collected apartments with evidence-based metrics (proximity, nearby amenities, composite scores) via a self-registering analyzer plugin framework | Mutating `Apartment`/`RawListing`; any AI, prediction, or live geocoding/places API call (explicitly out of scope) | [19_Analysis_Engine.md](19_Analysis_Engine.md) |
| `storage/` | All persistence: schema, migrations, repositories for apartments/search history/knowledge/platforms | Business rules about *what* to store (that belongs to the module producing the data) | [03_Data_Model.md](03_Data_Model.md) |
| `ranking/` | Score and order apartments against a `SearchRequest` | Fetching, storage writes | [08_Ranking_System.md](08_Ranking_System.md) |
| `services/` | Cross-cutting output services — currently just the HTML Report Generator | Ranking/analysis logic | [09_Report_System.md](09_Report_System.md) |
| `ui/` | Entry points a human runs (CLI in V1) | Business logic — a UI module only calls `core.agent` | [02_Folder_Guide.md](02_Folder_Guide.md) |
| `utils/` **(logging live since v2.0 Step 7)** | Generic helpers (logging, ID generation) with zero project-specific knowledge | Anything stateful or business-specific | [02_Folder_Guide.md](02_Folder_Guide.md) |
| `providers/` **(live; Production Provider Framework completed v2.5 Step 8)** | A common interface + factory + configuration + scoring router (with fallback) + health/metrics/statistics/validation, for both data providers (RentCast/local demo) and AI providers (Ollama/no-op) | Any actual fetching/parsing (delegates to `connectors/`), any formula/store the Knowledge Engine already owns (reused, not reimplemented), or business logic downstream of a search result | [21_Provider_Abstraction_Layer.md](21_Provider_Abstraction_Layer.md), [24_Production_Providers.md](24_Production_Providers.md) |

## The Independence Guardrail

Principle 7 ("business logic must remain independent from any individual website") is enforced structurally, not just by convention: **only `connectors/` may import or reference anything platform-specific** (a site's HTML structure, its API shape, its quirks). Every module downstream of `connectors/` operates exclusively on the shared `RawListing`/`Apartment` shapes defined in [03_Data_Model.md](03_Data_Model.md). A code reviewer's checklist question for any change to `analyzers/`, `ranking/`, `storage/`, or `services/`: *does this file need to know which website a listing came from?* If yes, that logic belongs in a connector, not here.

## Repository Writes vs. Service Layer

Made explicit in v2.0 Step 4.5 (architecture review), describing a rule the code had
already been following since Step 2 without ever writing it down: `analyzers/engine.py`
is allowed to call a `storage/*_repository.py` function **directly**, bypassing
`history_service.py`/`search_memory_service.py`, when the write is an **unconditional
append with no decision attached** — "record that this happened," full stop
(`apartment_repository.add_price_history` on a new apartment, `apartment_history_
repository.add_image_event`, `search_memory_repository.add_observed_apartment`). It
must go through the matching service function instead when the write depends on a
**decision** — does this field actually differ from what's stored
(`history_service.record_new_apartment`/`record_reobservation`), has anything changed
since the previous search (`search_memory_service.record_completed_search`). The
distinction: a repository call needs zero business logic to justify; routing an
unconditional append through a service function would only add an empty pass-through
wrapper, which is exactly the premature-abstraction [CLAUDE.md](../CLAUDE.md) warns
against. This does **not** loosen "storage/ must not contain business rules about what
to store" above — the decision, when there is one, still lives in `history_service.py`/
`search_memory_service.py`/`engine.py`, never in the repository itself.

## Extensibility Without Over-Engineering

Principle 6 ("support new countries, cities, rental types, and data sources without major redesign") is satisfied two different ways depending on the dimension, deliberately not the same way for all of them:

- **New data source (platform):** add one connector file implementing the existing contract, register it in the Platform Registry. Zero changes elsewhere. This is the dimension the architecture is built around from day one.
- **New city/country:** already supported — `SearchRequest` takes location as a parameter (see [04_Search_Request.md](04_Search_Request.md)); it's a data value, not a code path. A new country may need new connectors (platforms differ by country) but not a redesign.
- **New rental type:** *not* pre-built in V1.0 (see Non-Goals in [00_Project_Vision.md](00_Project_Vision.md)) — the `apartments` table and module names are concretely apartment-shaped, per Principle "no speculative generalization." The upgrade path if this is needed later is documented in [03_Data_Model.md](03_Data_Model.md) rather than built now: the `Connector`, `Analyzer`, and `Ranking` interfaces are already generic (they don't assume "apartment" in their method signatures), so adding a new rental type is primarily a storage-layer and data-model change, not a pipeline redesign.

This distinction matters: building a fully generic multi-type schema today, before a second rental type is ever requested, would violate the "don't design for hypothetical future requirements" rule in [CLAUDE.md](../CLAUDE.md). The architecture is extensible where extension is *known* to be needed (platforms), and has a documented (not pre-built) path where it's only *possible* to be needed (rental types).

## Technology Choices

| Decision | Choice | Why |
|---|---|---|
| Language/runtime | Python, project-local `.venv` | Already established — see [../learning/python_notes.md](../learning/python_notes.md) |
| Browser automation | Playwright + Chromium | Already installed — see [../learning/playwright_notes.md](../learning/playwright_notes.md); needed for platforms without a usable public API |
| **Storage engine** | **SQLite**, single file at `data/rental_intelligence.db` | Decided 2026-07-14. Needs real relational queries (price trend for one apartment, diff between two search runs) that flat JSON files make painful; single-machine/single-user in V1 so no server/concurrency needs; zero extra dependency (`sqlite3` is in the Python standard library); still a plain file, so it fits naturally under `data/` alongside the file-based folders. Full schema in [03_Data_Model.md](03_Data_Model.md). This closes the open item in [../learning/database_notes.md](../learning/database_notes.md). **Reconsidered 2026-07-14** against "hundreds of thousands of records, multiple countries": SQLite handles single-digit millions of rows with proper indexing without difficulty — the scale concern doesn't invalidate the choice by itself. What *would*: concurrent multi-writer access (e.g. multiple searches running in parallel processes) or true distributed/multi-machine deployment, neither of which is a v2.0 requirement. Kept as-is; PostgreSQL is the documented next step if either of those becomes real, not a speculative change now. |
| Raw content storage | Plain files under `data/raw_pages/`, `data/media/` — not in SQLite | Images and full HTML dumps don't belong in relational row storage; SQLite rows reference them by path |
| Report templating | Jinja2-style HTML templates in `services/report_templates/` | *Proposal, not yet locked* — see [09_Report_System.md](09_Report_System.md) |

## Open Questions

- ~~Which platform is the first connector target?~~ Resolved in v2.0 Step 7: RentCast.
  See [20_First_Production_Connector.md](20_First_Production_Connector.md) and
  [../notes/Questions.md](../notes/Questions.md).
