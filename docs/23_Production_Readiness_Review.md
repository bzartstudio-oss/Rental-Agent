# 23 — Production Readiness Review

Status: **Review only (2026-07-15) — no code changed.** Requested before implementing
additional production providers, to check the architecture's real scaling properties
against evidence (grep, read, and a few live checks) rather than restated design
intent. Every finding below cites the specific file/pattern it's based on.

---

## Part 1 — Production Readiness Report

### 1. Can this architecture scale to 100 connectors?

**The plugin/registration model: yes, already proven.** `ConnectorRegistry` is a plain
dict keyed by `platform_id` (O(1) lookup), and a connector is resolved by
`importlib.import_module(f"src.connectors.{connector_name}")` only on first use — no
central list to edit, no eager import of every connector at startup
(`src/connectors/sdk/registry.py`). The SDK Validation Sprint (docs/22) already proved
this empirically: a fourth connector was added with zero changes to any existing file.
Nothing about this mechanism degrades as the connector count grows from 4 to 100.

**The runtime orchestration model: no, not yet.** `RentalResearchAgent.run()`
(`src/core/agent.py`) queries every discovered platform in a single Python `for
platform in platforms:` loop — fully sequential, fully synchronous. There is no
concurrency anywhere in this codebase (confirmed: zero occurrences of `asyncio`,
`ThreadPoolExecutor`, or `await` outside Playwright's own internals). Two connectors
today means two round-trips back to back; 100 connectors means 100, and if any one of
them is slow (a real HTTP timeout, a slow page load), the entire search stalls behind
it — nothing times out the *loop*, only individual connectors time out themselves.

Compounding this: every HTML-based connector launches a **fresh Chromium process**
per call (`BrowserCollector.__enter__` in `src/collectors/browser_collector.py`) —
there's no shared browser instance reused across connectors within one search run, so
100 HTML connectors means 100 browser launches, not one browser with 100 pages.

**Verdict**: the *plugin* architecture scales to 100 connectors today. The
*execution* architecture does not — concurrency, a shared browser pool, enforced rate
limiting, and a circuit breaker for chronically-failing platforms (see Q2) would all
need to exist first. None of these are large rewrites, but none exist yet either.

### 2. Which modules are most likely to become bottlenecks?

In descending order of expected impact:

1. **`core/agent.py`'s per-platform loop** — sequential, synchronous, no per-platform
   timeout distinct from the connector's own. The primary bottleneck at any connector
   count above a handful.
2. **`collectors/browser_collector.py`** — one Chromium process launched per
   HTML-connector call, every search. Real, measurable startup cost multiplied by
   connector count.
3. **`analysis/pipeline.py` / `analysis/engine.py`** — every registered analyzer
   (11 today) runs for every apartment, sequentially, in Python, on every search —
   O(analyzers × apartments), no batching, no memoization. At 100 connectors each
   returning even 20–30 listings, this is thousands of apartments × 11 analyzers per
   search, all single-threaded.
4. **`discovery_agent._find_duplicate`** (`src/discovery/discovery_agent.py`) — a
   linear scan over every already-known platform, once per candidate, in
   `sync_platforms()` — O(n²) over the known-platforms list. Runs on every `ui/cli.py`
   startup (`DiscoveryAgent(db).sync_platforms(ALL_KNOWN_PLATFORMS)`, unconditional).
   Trivial at today's ~8 platforms; would start to matter in the low thousands, not at
   100 — included here because it's the one genuinely quadratic pattern already in
   the codebase, not because it's urgent yet.
5. **`search_memory_repository.find_previous_search()` / `get_search_history()`** —
   see Q3/Q4; already self-documented in the code as a known scaling limitation.

### 3. Are any database tables missing indexes?

Yes — three concrete gaps, found by reading `schema.sql`/migrations against the actual
query patterns in each repository:

- **`apartments` has no composite index on `(platform_id, platform_listing_id)`** —
  only a single-column index on `platform_id` (`idx_apartments_platform`,
  `schema.sql:62`). `apartment_repository.get_apartment_by_platform_listing()` filters
  on both columns together, and this is the dedup identity check
  (`analyzers/deduplicator.py`) run for **every listing, every connector, every
  search**. SQLite can use the single-column index to narrow to one platform's rows
  but must scan those for a `platform_listing_id` match — a composite index would make
  this a direct index lookup instead.
- **`knowledge_entries` has zero indexes beyond its primary key** — queried via
  `WHERE category = ? AND key = ?` (`reference_data_repository.get_knowledge_entry`)
  by every "nearby X" analyzer and both proximity analyzers, for every apartment, in
  every search (11 analyzers × N apartments per search). Invisible today because this
  table is still nearly empty (only illustrative demo data seeded so far) — the exact
  same shape of gap migration 0002 already found and fixed for `search_requests`.
- **`platform_performance_observations`/`apartment_analysis_metrics`** each have a
  single-column index (`platform_id`; `apartment_id`) but are actually queried with an
  `ORDER BY`/second filter (`observed_at`; `metric_name`) alongside it — a composite
  index would help once per-platform/per-apartment history grows large. Low urgency
  today; `get_recent_observations()` already bounds itself with `LIMIT`, so this is a
  secondary optimization, not a correctness or unbounded-growth concern.

### 4. Which operations are currently O(n) but should become indexed or cached later?

- **`find_previous_search()` / `get_search_history()`**
  (`src/storage/search_memory_repository.py`) — the code **already documents this
  itself**: *"Fetches every earlier `search_requests` row and filters by location in
  Python (`criteria_json` isn't indexed) — fine at this project's current scale;
  revisit with an indexed `location` column if search history ever grows large enough
  to matter."* `find_previous_search()` runs on **every completed search**
  (`search_memory_service.record_completed_search`), so total cost grows
  quadratically with search history, not linearly — the single most concrete,
  already-acknowledged debt item in the whole codebase.
- **`DiscoveryAgent.sync_platforms()`'s duplicate detection** — O(n²), see Q2.
- **Nothing is cached anywhere.** Grepped the entire `src/` tree for
  `cache`/`Cache`/`lru_cache`: zero real caching infrastructure exists — the only hit
  is a code comment about an unimplemented future thumbnail cache. Concretely:
  `platform_registry.get_platform()` is re-queried from SQLite for **every single
  report row** (added this session, `services/report_generator.py`) and inside every
  `DataProvider.search()` call — fine at today's row counts (`platforms` has ~8 rows),
  a natural candidate for a simple in-process cache once report/search volume grows,
  since a platform's identity rarely changes mid-run.
- **`AnalysisEngine` recomputes every analyzer for every apartment on every search**,
  even for an apartment whose relevant facts (coordinates, curated reference data)
  haven't changed since the previous search — no memoization keyed off
  `apartment_change_log`.

### 5. Which configuration values should be moved out of code?

**Already externalized (the right precedent, worth following elsewhere)**:
`RENTCAST_API_KEY`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL` — all real environment
variables, all with sane fallback behavior.

**Still hardcoded as module constants, no env/config override today**:

| Value | Location | Why it matters |
|---|---|---|
| `_PAGE_SIZE=100`, `_MAX_PAGES=3` | `connectors/rentcast/connector.py` | Quota-protective, but baked into one connector — a second real API-based connector needs its own hardcoded copy, not a shared setting |
| `_BACKOFF_BASE_SECONDS=0.5` | `connectors/rentcast/client.py` | Same — retry policy isn't a shared, reusable setting yet |
| `timeout_ms`, `max_retries`, `headless` defaults | `connectors/sdk/configuration.py` | Per-instance overridable in code, no fleet-wide env default |
| `_RECENT_WINDOW=20` | `knowledge/knowledge_service.py` | Rollup window size — a real tuning knob |
| `_MAX_SCORED_DISTANCE_KM` (2.0 / 5.0) | `analysis/analyzers/{public_transport,walking_distance}.py` | Scoring cutoffs, currently code-only |
| `_SATURATION_COUNT=5` | `analysis/analyzers/nearby_amenity.py` | Amenity-count scoring saturation point |
| `ScoringWeights` defaults (0.1/0.25/0.3/0.35) | `providers/scoring.py` | Already isolated into a dataclass (good), but not sourced from anywhere external |

None of these are wrong as defaults — the point is that changing any of them today
requires a code change and redeploy, not a config edit or environment override.

### 6. Which modules should become interfaces in the future?

- **`services/report_generator.py`** — one concrete HTML implementation, plain string
  templates, no `ReportGenerator` interface. A second output format (a PDF/JSON/email
  variant — already informally anticipated by the dead `reportlab`/`python-docx`
  dependencies and the long-gone `output/exports/` folder from the pre-architecture
  prototype) currently means forking the module, not implementing an adapter.
- **`ranking/ranking_engine.py`** — one concrete weighted-sum algorithm. If an
  ML-ranked or LLM-explained ranking mode is ever wanted (the reserved `src/ai/`
  folder was earmarked for exactly this back in v1.0), there's no `Ranker` interface
  to add a second strategy behind yet.
- **`storage/database.py` and every `*_repository.py` module** — hardcoded to raw
  `sqlite3.Connection` and `?`-style placeholders throughout, with no
  repository-interface layer between business logic and SQLite specifics. This is a
  deliberate, already-documented choice at today's scale
  (docs/01_System_Architecture.md "Storage Engine"), not an oversight — but it is the
  single largest rewrite this codebase would face if PostgreSQL (or any other engine)
  is ever adopted for concurrent-writer or distributed needs.
- **`collectors/browser_collector.py` / `http_collector.py`** — informally pluggable
  today (a connector overrides `_collect()` to swap transport, proven by both
  `RentCastConnector` and `SampleJsonFeedConnector`), but there's no formal
  `Collector` ABC — it works by convention, not by an enforced contract.

### 7. Which future integrations already have good extension points?

- **Maps / transport APIs — excellent, already built for this.** `src/analysis/`
  (`BaseAnalyzer`, self-registering `AnalysisRegistry`) was explicitly designed around
  this gap: `walking_distance.py`/`public_transport.py` already compute real
  great-circle math and are structurally ready for a live geocoding/transit API — that
  integration would mean writing (or upgrading) one analyzer, with zero changes to
  `AnalysisPipeline`, `AnalysisEngine`, or anything downstream.
- **ML — a good extension point exists, but ownership is split across two places.**
  `src/providers/ai/` (`AIProvider`, `OllamaAIProvider`, real router/fallback) is a
  genuinely working, live extension point for LLM-based features today. The older,
  still-empty `src/ai/` folder (reserved since v1.0 for "AI-assisted ranking
  explanations/report summaries") was never consolidated with it — two candidate
  homes for "AI/ML," not yet reconciled into one.
- **Notifications — no extension point exists at all.** Nothing in this codebase
  represents "notify someone that X happened" (a new listing, a price drop). Not a
  gap in otherwise-good design — it's simply unbuilt, and would start from a blank
  page rather than an existing pattern to extend.

### 8. Which technical debt should be resolved before Version 3.0?

**Cheap, zero-risk cleanup** (no design decision required):

- Five confirmed-dead dependencies in `requirements.txt` — `openai`, `reportlab`,
  `python-docx`, `pandas`, `numpy` — grepped: zero imports anywhere in `src/` or
  `tests/`. Leftover from the pre-architecture prototype and its abandoned PDF/export
  plans.
- Five empty, superseded `data/` subfolders — `apartments/`, `cache/`,
  `knowledge_base/`, `platform_registry/`, `search_history/` — all decided-against in
  favor of SQLite back in the v1.0 architecture pass, never deleted.
- The two missing indexes from Q3 (`apartments(platform_id, platform_listing_id)`,
  `knowledge_entries(category, key)`) — additive migrations, same shape as migration
  0002, zero risk.

**Real, load-bearing debt** (each is a genuine, non-trivial decision):

- `search_requests.location` living only inside `criteria_json`, never promoted to a
  real column — the direct cause of the two self-documented O(n) search-history
  scans (Q4). Fixing it is a schema decision (how to keep `SearchRequest`
  reproducibility intact while adding an indexed, queryable column), not a one-line
  patch.
- No enforced rate limiting despite a declared, inert `rate_limit_per_minute` field —
  every connector's throttling today is self-imposed and ad hoc (RentCast's own
  conservative pagination cap). At real scale this is a compliance/ToS risk, not just
  a performance one.
- No circuit breaker over chronically-failing connectors, despite the Knowledge
  Engine already computing the exact signal (`reliability_score`/`success_rate`) that
  would drive one — the data exists, nothing reads it for a routing decision.
- Fully sequential, synchronous connector querying — the single largest change needed
  before "100 connectors" is a real, practical operating mode rather than just a
  registry capacity claim.
- `src/ai/` vs. `src/providers/ai/` — resolve which one owns "AI/ML" before a third
  convention appears.

---

## Part 2 — Risk Assessment

| # | Risk | Likelihood at scale | Impact | Basis |
|---|---|---|---|---|
| 1 | Sequential, synchronous connector loop | High | High | Search latency scales linearly with connector count; one slow connector stalls the whole run |
| 2 | No enforced rate limiting | Medium–High | High | Real risk of ToS violations/API bans once real (non-demo) connectors multiply; today's safety is per-connector self-discipline, not systemic |
| 3 | `search_requests.location` unindexed (JSON-embedded) | Medium, grows with *usage* not connector count | Medium–High | Already self-documented O(n) scan on every completed search; compounds over time regardless of connector count |
| 4 | `knowledge_entries` missing index | Medium, only matters once curated data accumulates | Medium | 11 analyzers × every apartment × every search, once the table is no longer near-empty |
| 5 | No circuit breaker for failing connectors | Medium | Medium | Wasted time/retries on known-bad platforms; a performance/UX cost, not a correctness risk |
| 6 | SQLite single-writer model | Low under current single-process CLI usage | High if triggered | Already flagged and deliberately deferred (docs/01) — not new, but still the single largest structural limit if concurrent/distributed use is ever attempted |
| 7 | `src/ai/` vs. `providers/ai/` overlap | Low (no functional collision today) | Low–Medium | Real risk is a future contributor/agent building AI features in the wrong place, not a runtime failure |
| 8 | Dead dependencies (`openai`, `reportlab`, `python-docx`, `pandas`, `numpy`) | Low (unused code doesn't execute) | Low | Nonzero: unpatched CVEs in unused-but-installed packages still count as audit surface; `requirements.txt` overstates real capabilities |

Read top-to-bottom as rough priority order for "what would actually hurt first" if
connector count and usage both grow, not a formal quantitative model.

---

## Part 3 — Recommended Version 3.0 Roadmap

Sequenced so each phase unblocks the next, following this project's own established
pattern (storage before pipeline, SDK before a second connector) rather than tackling
items in isolation.

**Phase 0 — Cleanup (no design decisions, do first)**
- Remove the five confirmed-dead dependencies from `requirements.txt`.
- Delete the five empty, SQLite-superseded `data/` subfolders.
- Add the two missing indexes (`apartments(platform_id, platform_listing_id)`,
  `knowledge_entries(category, key)`) via one additive migration, following migration
  0002's exact precedent.

**Phase 1 — Concurrency in the orchestration loop**
- Introduce real concurrency (a thread pool is the smaller change; `asyncio` the
  larger, more thorough one) for `core/agent.py`'s per-platform loop — the single
  biggest blocker before "100 connectors" is a practical operating mode, not just a
  registry capacity.
- Pool/reuse a `BrowserCollector` instance across HTML-based connectors within one
  search run instead of one Chromium launch per connector.

**Phase 2 — Systemic rate limiting and circuit breaking**
- Build a real, enforced rate limiter that actually reads each connector's declared
  `rate_limit_per_minute` (currently inert data).
- Wire `platforms.reliability_score`/`success_rate` (already computed by the
  Knowledge Engine) into `DiscoveryAgent.discover()` or the orchestration loop, to
  skip or deprioritize chronically-failing platforms automatically.

**Phase 3 — Schema work enabling indexed search history**
- Promote `SearchRequest.location` to a real, indexed column alongside
  `criteria_json` (not replacing it — reproducibility still needs the full criteria
  serialized), resolving the two self-documented O(n) search-history scans.

**Phase 4 — Interface formalization (only once a second real implementation is
actually requested — consistent with this project's own "don't design for
hypothetical requirements" rule)**
- A `ReportGenerator` interface, if/when a second output format is actually
  requested.
- A `Ranker` interface, if/when an ML/LLM-based ranking mode is actually requested.
- Resolve `src/ai/` vs. `src/providers/ai/` — most likely retire the empty `src/ai/`
  in favor of the working `providers/ai/` package, unless "ranking explanations" is
  deliberately kept distinct from "summarization."

**Phase 5 — Storage engine reassessment (only if a real trigger occurs)**
- Re-evaluate SQLite vs. PostgreSQL only if/when concurrent multi-writer access or
  distributed deployment becomes a real, non-hypothetical requirement — the same
  deliberate "not now, revisit if this specific trigger happens" position
  docs/01_System_Architecture.md already recorded; this review found no new evidence
  that the trigger has occurred.

**Deliberately not included above**: Maps/transport-API integration and Notifications
are real Version 3.0-candidate *features*, not *technical debt* — the former already
has a good extension point (Q7) and can be added incrementally per-analyzer whenever
a vendor decision is made; the latter needs its own design pass from a blank page
whenever it's actually prioritized. Neither is a prerequisite for the phases above.
