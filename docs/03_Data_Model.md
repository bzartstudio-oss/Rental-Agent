# 03 — Data Model

Status: **v2.0 schema designed (2026-07-14); migration framework + schema live since Sprint
V2.0.1; `apartment_change_log`/`apartment_image_events` live since v2.0 Step 2;
`search_observed_apartments` and all nine `search_requests` v2.0 columns live since
v2.0 Step 3 (2026-07-14).** This doc reflects the target schema for the Autonomous
Rental Intelligence Platform upgrade (see [00_Project_Vision.md](00_Project_Vision.md)
"Mission"). Tables/columns marked **(v1.1, live)** exist in `storage/schema.sql` today.
Tables/columns marked **(v2.0, designed)** are schema-only so far (present in the
database via migration 0001, but no code writes/reads them yet) — see
[10_Roadmap.md](10_Roadmap.md) "Implementation Order" for what's live vs. still designed.
Storage engine unchanged: SQLite, single file at `data/rental_intelligence.db`.

## The Versioning Principle, Formalized

v1.0 established one rule for `apartments`/`search_results`. v2.0 extends it to **every**
entity in the system, now stated once, explicitly, as the pattern every table below
follows — not re-derived per table:

1. **A "current state" table** (`apartments`, `platforms`) holds exactly one row per
   entity, with mutable summary columns — but every mutable column is either (a) set
   once and never changed (`first_seen_at`, `created_at`), or (b) a denormalized rollup
   whose full history lives in an append-only table below it. The current-state row is a
   *view*, never the only copy of the truth.
2. **A dedicated append-only history table** exists for every field that is queried often
   enough, or important enough, to deserve its own indexed table and explicit schema —
   currently: price, availability/status, image add/remove events, platform performance
   observations.
3. **A generic append-only change-log table** (`apartment_change_log`) catches every other
   field (title, description, and whatever's added later) without requiring a schema
   migration per field. This is the direct answer to "must be addable without changing
   existing code": a new trackable field needs a new *call site* logging to the existing
   table, not a new table.
4. **An immutable snapshot table** (`search_results`) exists wherever "what did a report
   say at the time" must never silently change later, even as the entities it references
   keep accumulating history.
5. **Nothing is ever `DELETE`d.** "Unsupported," "removed," "delisted" are all states
   recorded by inserting a new row or flipping a status column — the old state stays
   queryable. `mark_connector_unavailable()` (v1.1) is the existing example of this;
   apartments/platforms never get deleted either, even if a platform shuts down.

Every table below is one of these four kinds. When adding a new one, name which kind it
is — that's what keeps this principle from eroding one convenient exception at a time.

## Entities

### `platforms` — extended (v1.1 live + v2.0 designed columns)

The Platform Registry (see [05_Platform_Discovery.md](05_Platform_Discovery.md)). v2.0
adds **Platform Intelligence**: rollup performance metrics, kept current by the Knowledge
Engine after every search (see [16_Knowledge_Engine.md](16_Knowledge_Engine.md)).

| Column | Type | Status | Notes |
|---|---|---|---|
| `id` | TEXT PK | v1.1 | Stable slug |
| `name` | TEXT | v1.1 | — |
| `country` | TEXT | v1.1 | — |
| `supported_cities` | TEXT (JSON list) | v1.1 | — |
| `rental_types` | TEXT (JSON list) | v1.1 | — |
| `homepage` | TEXT | v1.1 | — |
| `search_url` | TEXT, nullable | v1.1 | — |
| `requires_login` | INTEGER (bool) | v1.1 | — |
| `connector_available` | INTEGER (bool) | v1.1 | — |
| `connector_name` | TEXT, nullable | v1.1 | — |
| `connector_version` | TEXT, nullable | **v2.0** | Set by whoever last touched the connector's parsing logic — lets a sudden extraction-quality shift in Knowledge Engine data be correlated with "the connector changed" vs. "the platform changed" |
| `last_verified` | TEXT (ISO 8601), nullable | v1.1 | — |
| `discovery_method` | TEXT | v1.1 | — |
| `notes` | TEXT, nullable | v1.1 | — |
| `reliability_score` | REAL, nullable | **v2.0** | Rollup, 0–1. Recomputed after every search from `platform_performance_observations` — see [16_Knowledge_Engine.md](16_Knowledge_Engine.md) |
| `success_rate` | REAL, nullable | **v2.0** | Rollup — fraction of recent searches where this platform's connector didn't fail |
| `avg_response_time_ms` | REAL, nullable | **v2.0** | Rollup |
| `avg_apartment_count` | REAL, nullable | **v2.0** | Rollup — typical result-set size, useful for spotting a broken connector returning 0 or a suspiciously huge number |
| `duplicate_percentage` | REAL, nullable | **v2.0** | Rollup — see [16_Knowledge_Engine.md](16_Knowledge_Engine.md) "Duplicate Rate" for the precise definition |
| `created_at` | TEXT (ISO 8601) | v1.1 | — |

All six rollup columns are nullable and start `NULL` — a platform with zero observed
searches has no rollup yet, which is a real, honest state (not `0`, which would falsely
imply "confirmed 0% reliable").

### `apartments` — extended (v1.1 live + v2.0 designed columns)

Current state, one row per (platform, platform's own listing ID).

| Column | Type | Status | Notes |
|---|---|---|---|
| `id` | TEXT PK | v1.1 | Synthetic UUID |
| `platform_id` | TEXT FK → `platforms.id` | v1.1 | — |
| `platform_listing_id` | TEXT | v1.1 | — |
| `title` | TEXT | v1.1 | Current value — history in `apartment_change_log` |
| `description` | TEXT, nullable | **v2.0 (new field)** | Not captured at all pre-v2.0 — required to exist before its changes can be tracked. Connectors populate it if the platform provides one; `RawListing` gains a matching field |
| `bedrooms` / `bathrooms` / `sqft` | REAL, nullable | v1.1 | — |
| `address_raw` | TEXT | v1.1 | — |
| `address_normalized` | TEXT (JSON), nullable | v1.1 | — |
| `latitude` / `longitude` | REAL, nullable | v1.1 | — |
| `url` | TEXT | v1.1 | — |
| `current_price` | REAL | v1.1 | Rollup of `apartment_price_history` |
| `current_status` | TEXT | v1.1 | Rollup of `apartment_availability_history` |
| `first_seen_at` / `last_seen_at` | TEXT (ISO 8601) | v1.1 | — |
| `merged_into_id` | TEXT FK → `apartments.id`, nullable | v1.1 | Still unused — V2/cross-platform dedup, unchanged by this upgrade |

**Unique constraint:** (`platform_id`, `platform_listing_id`) — unchanged from v1.1.

### `apartment_price_history` (v1.1, live — unchanged)

Append-only. `id`, `apartment_id` FK, `price`, `observed_at`, `search_id` FK nullable.

### `apartment_availability_history` (v1.1, live — unchanged)

Append-only. `id`, `apartment_id` FK, `status`, `observed_at`, `search_id` FK nullable.

### `apartment_change_log` — new (v2.0 Step 2, live)

The generic history table described in "The Versioning Principle" above — catches title,
description, and any future trackable field without a schema migration.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `apartment_id` | TEXT FK → `apartments.id` | — |
| `field_name` | TEXT | e.g. `"title"`, `"description"` |
| `old_value` | TEXT, nullable | Null for the first-ever observation of a field |
| `new_value` | TEXT | — |
| `search_id` | TEXT FK → `search_requests.id`, nullable | — |
| `observed_at` | TEXT (ISO 8601) | — |

A row is written only when `new_value != old_value`, mirroring the change-detection rule
already used for price/availability (see [07_Analysis_Engine.md](07_Analysis_Engine.md)).
Not used for `price`/`status` — those keep their dedicated, more heavily-queried tables.

### `apartment_images` — extended (v1.1 live + v2.0 designed columns)

| Column | Type | Status | Notes |
|---|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | v1.1 | — |
| `apartment_id` | TEXT FK → `apartments.id` | v1.1 | — |
| `source_url` | TEXT | v1.1 | — |
| `local_path` | TEXT | v1.1 | — |
| `thumbnail_path` | TEXT, nullable | **v2.0** | Optional cached thumbnail — requirement "optionally cache thumbnails." Populated lazily, not required for every image |
| `position` | INTEGER | v1.1 | — |
| `is_current` | INTEGER (bool) | **v2.0**, default `1` | Whether this image is still present on the listing as of the most recent observation — see `apartment_image_events` below. Never deleted when an image is removed; flipped to `0` instead |
| `downloaded_at` | TEXT (ISO 8601) | v1.1 | — |

### `apartment_image_events` — new (v2.0 Step 2, live)

Append-only log of images appearing/disappearing between searches — the "detect image
changes between executions" requirement.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `apartment_id` | TEXT FK → `apartments.id` | — |
| `event` | TEXT | `"added"` or `"removed"` |
| `source_url` | TEXT | — |
| `search_id` | TEXT FK → `search_requests.id` | Which search detected the change |
| `observed_at` | TEXT (ISO 8601) | — |

### `search_observed_apartments` — new (v2.0 Step 3, live)

Every apartment observed during a search — the **full** set, not just the ranked/filtered
subset in `search_results`. Exists specifically so run-over-run comparison
([17_Search_Memory.md](17_Search_Memory.md)) reflects "what changed in the world," not
"what changed within one particular budget filter" — an apartment that drops out of
`search_results` because a filter excluded it is not the same event as one that's
actually gone from the platform, and only this table can tell the two apart.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `search_id` | TEXT FK → `search_requests.id` | — |
| `apartment_id` | TEXT FK → `apartments.id` | — |
| `observed_at` | TEXT (ISO 8601) | — |

One row per (search, apartment) — written by the Analysis Engine for every listing it
processes in a run, regardless of whether that apartment later survives ranking/filtering.

### `search_requests` — extended (v1.1 live + v2.0 Step 3 live columns)

v2.0 is what turns this into **Search Memory** (requirement 3) — the record of a search
grows from "what was asked" (v1.1) to "what was asked and what happened." All nine
columns below are now filled in by `storage/search_memory_repository.py::complete_search_execution`,
called from `RentalResearchAgent.run()` once a search finishes (v2.0 Step 3).

| Column | Type | Status | Notes |
|---|---|---|---|
| `id` | TEXT PK (UUID) | v1.1 | — |
| `created_at` | TEXT (ISO 8601) | v1.1 | — |
| `criteria_json` | TEXT (JSON) | v1.1 | — |
| `label` | TEXT, nullable | v1.1 | — |
| `execution_time_ms` | INTEGER, nullable | **v2.0** | Total wall-clock time for `RentalResearchAgent.run()`, written after completion |
| `discovered_platform_ids_json` | TEXT (JSON list), nullable | **v2.0** | Every platform `DiscoveryAgent.discover()` returned as a candidate |
| `searched_platform_ids_json` | TEXT (JSON list), nullable | **v2.0** | Subset actually queried successfully (excludes ones whose connector raised) |
| `apartment_count` | INTEGER, nullable | **v2.0** | Total listings processed this run |
| `new_apartment_count` | INTEGER, nullable | **v2.0** | Not seen in the previous comparable run — see [17_Search_Memory.md](17_Search_Memory.md) "Run-Over-Run Comparison" |
| `removed_apartment_count` | INTEGER, nullable | **v2.0** | Present in the previous comparable run, absent this time |
| `changed_apartment_count` | INTEGER, nullable | **v2.0** | Present in both, but with at least one price/status/title/description change |
| `report_path` | TEXT, nullable | **v2.0** | Where the generated report landed |
| `runtime_stats_json` | TEXT (JSON), nullable | **v2.0** | Free-form bag for anything not worth its own column yet (per-platform timing breakdown, error messages) — same escape-hatch role `notes` plays elsewhere |

All nine new columns are nullable and `NULL` until `run()` completes — a row is inserted
with just the v1.1 columns at submission time (unchanged), then updated once execution
finishes. This is a rare, deliberate exception to "never `UPDATE`, only `INSERT`": these
columns describe *this run's own execution*, not an external fact that could have
multiple true values over time the way an apartment's price can — there's nothing to
version, only a value to fill in once.

### `search_results` (v1.1, live — unchanged)

Immutable snapshot. `id`, `search_id` FK, `apartment_id` FK, `rank`, `score`,
`score_breakdown_json`, `price_at_search`, `status_at_search`.

### `platform_performance_observations` — new (v2.0, designed)

The Knowledge Engine's raw, append-only memory — one row per (platform, search). See
[16_Knowledge_Engine.md](16_Knowledge_Engine.md) for what each metric means and how it's
computed; `platforms`' six rollup columns are aggregates *over* this table, recomputed
after each insert.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `platform_id` | TEXT FK → `platforms.id` | — |
| `search_id` | TEXT FK → `search_requests.id` | — |
| `results_count` | INTEGER | — |
| `failed` | INTEGER (bool) | Connector raised or returned nothing when something was expected |
| `response_time_ms` | INTEGER, nullable | Null if `failed` before any response |
| `extraction_quality_score` | REAL, nullable | 0–1, fraction of expected fields (title/price/url at minimum) successfully parsed per listing, averaged |
| `image_quality_score` | REAL, nullable | 0–1, fraction of listings with at least one usable image |
| `availability_quality_score` | REAL, nullable | 0–1, fraction of listings with a resolvable status (vs. unknown/unparseable) |
| `duplicate_rate` | REAL, nullable | 0–1, fraction of this platform's raw listings in this run that were exact/near duplicates of each other (a connector/data-quality signal — distinct from `apartments.merged_into_id`, which is cross-platform and still V2) |
| `ranking_usefulness_score` | REAL, nullable | 0–1, *TBD exact formula* — proposed: fraction of this platform's listings that ended up in the top N of `search_results` versus its share of total candidates, as a proxy for "did this platform's results actually compete" |
| `parsing_success` | INTEGER (bool) | Whether the connector's `_parse()` completed without raising, independent of whether individual field extraction was perfect |
| `observed_at` | TEXT (ISO 8601) | — |

### `filter_definitions` — new (v2.0, designed)

Metadata registry for the Dynamic Filter Engine (see
[04_Search_Request.md](04_Search_Request.md)) — what filters *exist*, kept queryable as
data so nothing (a future UI, a validation tool) needs to read Python source to know.
The actual matching/scoring *logic* stays in `search/filters/` code — see that doc for
why data alone can't replace it.

| Column | Type | Notes |
|---|---|---|
| `key` | TEXT PK | Matches the key used in `SearchRequest.criteria` and the `FilterDefinition` registry |
| `display_name` | TEXT | Human-readable, for a future UI |
| `category` | TEXT | `"budget"`, `"availability"`, `"amenity"`, `"proximity"`, `"score"`, etc. — see [04_Search_Request.md](04_Search_Request.md) for the full category list |
| `value_type` | TEXT | `"number"`, `"boolean"`, `"enum"`, `"date"` |
| `applicable_rental_types_json` | TEXT (JSON list) | Which `rental_types` this filter makes sense for (e.g. `"private_bathroom"` doesn't apply to a whole-house rental) |
| `description` | TEXT, nullable | — |
| `created_at` | TEXT (ISO 8601) | — |

### `apartment_analysis_metrics` — new (v2.0, designed)

The Deep Analysis Engine's output store (see
[07_Analysis_Engine.md](07_Analysis_Engine.md)) — generic key/value so a new metric type
(a "future environmental indicator," as the mission spec puts it) doesn't need a schema
migration.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `apartment_id` | TEXT FK → `apartments.id` | — |
| `metric_name` | TEXT | e.g. `"walking_distance_minutes"`, `"lifestyle_score"`, `"nearby_supermarket_count"` |
| `metric_value` | REAL | — |
| `metric_unit` | TEXT, nullable | e.g. `"minutes"`, `"count"`, `"score_0_1"` |
| `source_module` | TEXT | Which analyzer computed this — e.g. `"analyzers.distance"`, `"analyzers.scores"` |
| `search_id` | TEXT FK → `search_requests.id`, nullable | Which run computed/refreshed this value |
| `computed_at` | TEXT (ISO 8601) | — |

Append-only like everything else here: a metric that changes (e.g. a new bus line changes
`transit_score`) gets a new row, not an overwrite — "the user must later be able to
compare apartment evolution" applies to computed metrics too, not just scraped fields.

### `knowledge_entries` (v1.1, live — unchanged)

Curated reference data. `id`, `category`, `key`, `value_json`, `source`, `updated_at`.

### `raw_captures` (v1.1, live — unchanged)

Audit trail. `id`, `platform_id` FK, `apartment_id` FK nullable, `search_id` FK,
`raw_page_path`, `captured_at`.

## Entity Relationship Summary

```
platforms 1──* apartments 1──* apartment_price_history
   │                      │ 1──* apartment_availability_history
   │                      │ 1──* apartment_change_log         (NEW)
   │                      │ 1──* apartment_images 1──* apartment_image_events  (NEW)
   │                      │ 1──* apartment_analysis_metrics   (NEW)
   │                      │ *──* search_results ──* search_requests
   │                      │ *──* search_observed_apartments ──* search_requests  (NEW)
   │                      │
   │                      *──* raw_captures ──* search_requests
   │
   1──* platform_performance_observations ──* search_requests   (NEW)

filter_definitions — standalone metadata, not FK-linked   (NEW)
knowledge_entries  — standalone, not FK-linked
```

## Storage Format Outside SQLite

Unchanged from v1.1 (see [02_Folder_Guide.md](02_Folder_Guide.md)): `media/` and
`raw_pages/` remain file-based; `data/apartments/`, `search_history/`,
`platform_registry/` remain superseded/legacy; `cache/` remains outside the database. New
in v2.0: `thumbnail_path` (on `apartment_images`) points into `data/media/` alongside the
full-size image, not a new top-level folder.

## Open Questions

- Exact `status` vocabulary for `apartment_availability_history` / `current_status` (carried over from v1.1, still open).
- Exact formula for `ranking_usefulness_score` — proposed above, not yet validated against real data.
- See [../notes/Questions.md](../notes/Questions.md) for what's still open elsewhere.
