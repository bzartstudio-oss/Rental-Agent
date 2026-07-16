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
| `ranking_usefulness_score` | REAL, nullable | Not bounded to 0–1 (can exceed 1) — implemented in v2.0 Step 4 (`src/knowledge/metrics.py::ranking_usefulness_score`): (platform's fraction of the top-`N` ranked apartments) ÷ (platform's fraction of all candidates this run), `N = 10`. See [16_Knowledge_Engine.md](16_Knowledge_Engine.md) |
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

### `apartment_analysis_metrics` — new (v2.0 Step 6, live)

The Deep Analysis Engine's output store (see
[19_Analysis_Engine.md](19_Analysis_Engine.md)) — generic key/value so a new metric type
(a "future environmental indicator," as the mission spec puts it) doesn't need a schema
migration. `confidence`/`evidence_json`/`analyzer_version` were added in migration 0003
(v2.0 Step 6) once the richer `AnalyzerResult` shape (Score/Confidence/Evidence/
Timestamp/Version/Source) needed more than the four columns originally designed here.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `apartment_id` | TEXT FK → `apartments.id` | — |
| `metric_name` | TEXT | e.g. `"walking_distance"`, `"nearby_supermarkets"`, `"composite:location_score"` |
| `metric_value` | REAL, `NOT NULL` | The analyzer's score — never written when there's no evidence, see [19_Analysis_Engine.md](19_Analysis_Engine.md) "Analysis History" |
| `metric_unit` | TEXT, nullable | Unused by any built-in analyzer so far (every score is unitless, 0–1) |
| `source_module` | TEXT | Which analyzer computed this — e.g. `"haversine_calculation"`, `"knowledge_entries"`, `"src.analysis.scoring"` |
| `search_id` | TEXT FK → `search_requests.id`, nullable | Which run computed/refreshed this value |
| `computed_at` | TEXT (ISO 8601) | Shared across every metric from the same analysis run — see `AnalysisContext` |
| `confidence` | REAL, nullable | **v2.0 Step 6.** 0–1, how much evidence backs this score |
| `evidence_json` | TEXT (JSON), nullable | **v2.0 Step 6.** `{"evidence": [...], "warnings": [...]}` — human-readable strings, not re-derivable data |
| `analyzer_version` | TEXT, nullable | **v2.0 Step 6.** Which version of the analyzer produced this row |

Append-only like everything else here: a metric that changes (e.g. a new bus line changes
`transit_score`) gets a new row, not an overwrite — "the user must later be able to
compare apartment evolution" applies to computed metrics too, not just scraped fields.

### `feedback_events` — new (v2.5 Step 12, live)

The User Feedback and Preference Learning Engine's append-only raw log (see
[28_User_Feedback_and_Preference_Learning.md](28_User_Feedback_and_Preference_Learning.md)).
No `update_*`/`delete_*` function exists anywhere for this table — the only way to
"change" recorded history is to add a new row.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `event_id` | TEXT, `UNIQUE`, `NOT NULL` | A real UUID, generated when the `FeedbackEvent` is constructed |
| `profile_id` | TEXT, `NOT NULL` | Which user/profile this event belongs to |
| `search_id` | TEXT FK → `search_requests.id`, nullable | Which search execution this event happened during, if any |
| `apartment_id` | TEXT, nullable | Which listing this event concerns, if any (no FK — see this doc's own reasoning for `raw_captures.apartment_id`: historical feedback must still be understandable even if the apartment later changes) |
| `event_type` | TEXT | One of `FeedbackEventType`'s named constants, or any future string — never validated against a closed set |
| `event_value_json` | TEXT (JSON) | A rating, a filter key/value, a weight delta — shape varies by `event_type` |
| `occurred_at` | TEXT (ISO 8601) | — |
| `source` | TEXT | e.g. `"cli"`, `"search_request"` |
| `session_id` | TEXT, nullable | — |
| `metadata_json` | TEXT (JSON) | Free-form, caller-supplied context |
| `ranking_profile_json` | TEXT (JSON), nullable | A snapshot of the active `RankingProfile` weights at the time |
| `search_filters_json` | TEXT (JSON), nullable | A snapshot of the active search criteria at the time |

### `preference_observations` — new (v2.5 Step 12, live)

One `PreferenceRule`'s verdict on one `feedback_events` row, persisted once at
`record_event()` time — a preference profile rebuilt later reproduces already-
computed observations, never silently re-derives different ones.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `profile_id` | TEXT | — |
| `preference_key` | TEXT | e.g. `"walking_distance"`, `"private_bathroom"` |
| `event_id` | TEXT FK → `feedback_events.event_id` | — |
| `direction` | TEXT | `"supporting"` or `"opposing"` |
| `magnitude` | REAL | This observation's own strength, `[0, 1]`, before decay/confidence weighting |
| `observed_value_json` | TEXT (JSON), nullable | The raw value this observation carried (a price, a category, a numeric threshold) |
| `source_type` | TEXT | `"explicit"` or `"inferred"` |
| `computed_at` | TEXT (ISO 8601) | — |
| `explanation` | TEXT | Human-readable — becomes part of `explain_preference()`'s output |

### `preference_adjustments` — new (v2.5 Step 12, live)

One row per time a preference's *computed* value/confidence actually changed —
the source of truth for "current" values (see docs/28 "Auditability"). Append-only:
`undo_preference_adjustment()`/`reset_inferred_preferences()` write new rows
reversing/resetting a prior one, never delete or update the original.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `profile_id` | TEXT | — |
| `preference_key` | TEXT | — |
| `previous_value_json` / `new_value_json` | TEXT (JSON), nullable | `NULL` `new_value_json` means "reset to neutral" |
| `previous_confidence` / `new_confidence` | REAL, nullable | — |
| `reason` | TEXT | e.g. `"Recomputed from 4 observation(s)"`, `"Reset inferred preference to neutral"` |
| `triggered_by_event_ids_json` | TEXT (JSON) | Which `feedback_events` caused this adjustment |
| `adjustment_type` | TEXT | `"inferred"` \| `"explicit"` \| `"undo"` \| `"reset"` |
| `reverses_adjustment_id` | INTEGER FK → `preference_adjustments.id`, nullable | Set only on an `"undo"` row |
| `applied_at` | TEXT (ISO 8601) | Also the new evidence cutoff for future rebuilds when `adjustment_type` is `"reset"`/`"undo"` |

### `preference_snapshots` — new (v2.5 Step 12, live)

A versioned, full-profile serialization at a point in time — for
`compare_preference_profiles()`/history browsing.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `profile_id` | TEXT | — |
| `snapshot_json` | TEXT (JSON) | Every preference's `current_value`/`confidence`/`is_explicit` at `created_at` |
| `reason` | TEXT | e.g. `"build_preference_profile"` |
| `created_at` | TEXT (ISO 8601) | — |

### `discovery_runs` — new (v2.5 Step 13, live)

One row per `AutomaticDiscoveryAgent.run()` execution (see
[29_Automatic_Platform_Discovery.md](29_Automatic_Platform_Discovery.md)). The one table
here with a real, documented mutation after insert: `update_run_summary()` fills in
`completed_at`/the six summary counters once the pipeline finishes — every other table
below is strictly append-only.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `run_id` | TEXT, `UNIQUE`, `NOT NULL` | A real UUID |
| `request_json` | TEXT (JSON) | The full `DiscoveryRequest`, so a run's exact parameters are always reproducible |
| `started_at` / `completed_at` | TEXT (ISO 8601), `completed_at` nullable | — |
| `providers_used_json` | TEXT (JSON) | Which `DiscoveryProvider`s actually ran (a skipped-refresh run has `[]`) |
| `total_candidates` / `new_candidate_count` / `duplicate_count` / `verified_count` / `supported_count` / `unsupported_count` | INTEGER | Summary counters, written once by `update_run_summary()` |
| `notes` | TEXT, nullable | Warnings joined into one string (e.g. a failed provider, a skipped refresh) |

### `platform_candidates` — new (v2.5 Step 13, live)

One *current-state* row per unique discovered candidate — mutable, like `platforms`
itself, since classification/status/confidence genuinely change as more evidence
arrives. **Never the canonical registry**: promotion to a real `platforms` row only
ever happens through the existing `DiscoveryAgent.sync_platforms()` path (see docs/29
"Registry Integration"), never automatically.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `candidate_id` | TEXT, `UNIQUE`, `NOT NULL` | A real UUID, stable across every run that re-discovers this same normalized domain |
| `normalized_domain` | TEXT | The dedup key — see docs/29 "Deduplication" |
| `name` | TEXT | — |
| `raw_url` | TEXT | The literal URL a provider handed back |
| `country` / `region` / `city` | TEXT, nullable | From the `DiscoveryRequest` that first found this candidate |
| `status` | TEXT | One of `PlatformStatus`'s 12 values |
| `classification` | TEXT | One of `PlatformClassification`'s 13 values |
| `confidence` | REAL, nullable | `[0, 1]`, deterministic — see docs/29 "Confidence Calculation" |
| `matched_platform_id` | TEXT FK → `platforms.id`, nullable | Set when this candidate matches an existing registry platform by normalized domain |
| `first_discovered_at` / `last_seen_at` | TEXT (ISO 8601) | `first_discovered_at` never changes after insert |
| `last_run_id` | TEXT FK → `discovery_runs.run_id` | Which run most recently touched this candidate |

### `platform_evidence` — new (v2.5 Step 13, live)

Append-only: "Never overwrite evidence" (the mission's own words) — no `update_*`/
`delete_*` function exists anywhere for this table.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `candidate_id` | TEXT FK → `platform_candidates.candidate_id` | — |
| `run_id` | TEXT FK → `discovery_runs.run_id` | — |
| `evidence_type` | TEXT | One of the mission's 15 named evidence types (e.g. `"discovered_url"`, `"page_title"`, `"location_evidence"`) |
| `discovery_provider` | TEXT | Which provider produced this row |
| `value_json` | TEXT (JSON) | Shape varies by `evidence_type` |
| `confidence` | REAL, nullable | — |
| `collected_at` | TEXT (ISO 8601) | — |

### `platform_verification_observations` — new (v2.5 Step 13, live)

Append-only. "Verification failures must not erase a platform" (the mission's own
words): a failed check is recorded honestly here, never removes the candidate row.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `candidate_id` | TEXT FK → `platform_candidates.candidate_id` | — |
| `run_id` | TEXT FK → `discovery_runs.run_id` | — |
| `check_type` | TEXT | e.g. `"domain_accessibility"`, `"listing_or_search_page_presence"`, `"login_requirement"` |
| `result` | TEXT | `"pass"` / `"fail"` / `"unknown"` for most checks; `login_requirement` uses the more explicit `"login_required"` / `"no_login_required"` instead of ambiguous pass/fail |
| `detail_json` | TEXT (JSON), nullable | e.g. matched keyword markers, HTTP status code |
| `observed_at` | TEXT (ISO 8601) | — |

### `platform_capability_estimates` — new (v2.5 Step 13, live)

Append-only. `is_estimate` is always `1` (`True`) — nothing in this sprint confirms a
capability via a real connector.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `candidate_id` | TEXT FK → `platform_candidates.candidate_id` | — |
| `run_id` | TEXT FK → `discovery_runs.run_id` | — |
| `capability_key` | TEXT | One of the mission's 14 named capabilities (e.g. `"images"`, `"api_or_feed"`, `"likely_connector_complexity"`) |
| `estimated_value_json` | TEXT (JSON) | Shape varies by `capability_key` |
| `is_estimate` | INTEGER (bool) | Always `1` |
| `observed_at` | TEXT (ISO 8601) | — |

### `platform_duplicate_links` — new (v2.5 Step 13, live)

Append-only. "Store duplicate relationships rather than deleting duplicate evidence"
(the mission's own words) — a candidate identified as a duplicate keeps its own row
and evidence; only this link records the relationship.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `candidate_id` | TEXT FK → `platform_candidates.candidate_id` | The duplicate |
| `duplicate_of_candidate_id` | TEXT FK → `platform_candidates.candidate_id` | The canonical candidate it duplicates |
| `matched_by` | TEXT | e.g. `"normalized_name"` |
| `linked_at` | TEXT (ISO 8601) | — |

### `discovery_provider_observations` — new (v2.5 Step 13, live)

Append-only, one row per provider execution within a run — this sprint's whole
"Knowledge Engine Integration" answer (see docs/29): `statistics.compute_discovery_
statistics()` aggregates this table for provider effectiveness/runtime/failure rates.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `run_id` | TEXT FK → `discovery_runs.run_id` | — |
| `provider_id` | TEXT | — |
| `candidates_found` | INTEGER | 0 on failure |
| `duration_ms` | INTEGER, nullable | — |
| `succeeded` | INTEGER (bool) | — |
| `error` | TEXT, nullable | Set only when `succeeded` is false |
| `observed_at` | TEXT (ISO 8601) | — |

### `saved_searches` — new (v2.5 Step 14, live)

One *current-state* row per saved search — mutable, like `platforms`, but the
actual search definition never changes in place; see `saved_search_versions`
below. `update_saved_search_metadata()` refreshes `name`/`description`/
`current_version`/`enabled`/`updated_at` only.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `saved_search_id` | TEXT, `UNIQUE`, `NOT NULL` | A real UUID |
| `profile_id` | TEXT, nullable | Feedback profile this saved search is associated with, if any |
| `name` / `description` | TEXT | — |
| `current_version` | INTEGER | Points at the `saved_search_versions` row in effect |
| `enabled` | INTEGER (bool) | Disabled saved searches are excluded from `due_saved_searches()` |
| `created_at` / `updated_at` | TEXT (ISO 8601) | `created_at` never changes after insert |

### `saved_search_versions` — new (v2.5 Step 14, live)

Append-only: "Never overwrite a saved search definition. Every modification
creates a new SavedSearchVersion" (the mission's own words) — one immutable
row per edit, `UNIQUE (saved_search_id, version)`.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `saved_search_id` | TEXT FK → `saved_searches.saved_search_id` | — |
| `version` | INTEGER | 1, 2, 3, ... per saved search |
| `request_json` | TEXT (JSON) | `{"location": ..., "criteria": {...}}` — exactly `SearchRequest.to_criteria_json()`'s own shape |
| `active_filters_json` | TEXT (JSON) | `FilterConfiguration`'s own fields (`enabled_filter_keys`, `strict_validation`) — not criteria values, which live in `request_json` |
| `ranking_profile_json` | TEXT (JSON), nullable | `{"name", "description", "weights": {...}}` |
| `feedback_mode` | TEXT, nullable | One of `FeedbackMode`'s values |
| `selected_platforms_json` / `selected_connectors_json` | TEXT (JSON) | Allowlists — empty means "every connector-available platform" |
| `geographic_destinations_json` | TEXT (JSON) | e.g. `[{"country": "Spain", "region": "Valencia", "city": "Valencia"}]` — used only when `discovery_refresh_before_monitoring` is set |
| `monitoring_policy_json` | TEXT (JSON) | The full `MonitoringPolicy.as_dict()` |
| `report_options_json` / `retention_policy_json` / `tags_json` / `metadata_json` | TEXT (JSON) | — |
| `created_at` | TEXT (ISO 8601) | — |

### `monitoring_schedules` — new (v2.5 Step 14, live)

One current-state row per saved search — doubles as the "when is this due"
bookkeeping and the run-claim lock. `claim_due_run()` is the one atomic
conditional `UPDATE`; `release_run_claim()` and `update_schedule()` are the
other two mutation functions for this table.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `saved_search_id` | TEXT, `UNIQUE`, FK → `saved_searches.saved_search_id` | — |
| `next_run_at` | TEXT (ISO 8601), nullable | `NULL` means manual-only (no scheduling policy field set) |
| `last_run_at` / `last_run_status` | TEXT, nullable | — |
| `claimed_by` | TEXT, nullable | Worker id currently holding the claim |
| `claimed_at` / `claim_expires_at` | TEXT (ISO 8601), nullable | An expired claim (`claim_expires_at < now`) can be re-claimed by anyone |

### `monitoring_runs` — new (v2.5 Step 14, live)

One append-only header row per `MonitoringEngine._execute()` call. The one
documented mutation after insert: `update_run_status()` fills in `status`/
`search_id`/`completed_at`/the two outcome lists/`event_count`/`notes` once
the pipeline finishes.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `monitoring_run_id` | TEXT, `UNIQUE`, `NOT NULL` | A real UUID |
| `saved_search_id` | TEXT FK → `saved_searches.saved_search_id` | — |
| `saved_search_version` | INTEGER | Which immutable version this run executed |
| `search_id` | TEXT, nullable, FK → `search_requests.id` | `NULL` only if the run failed before `RentalResearchAgent.run()` was even called |
| `status` | TEXT | One of `MonitoringRunStatus`'s 4 values (`running`/`completed`/`partial`/`failed`) |
| `started_at` / `completed_at` | TEXT (ISO 8601), `completed_at` nullable | — |
| `platforms_attempted_json` / `platforms_succeeded_json` / `platforms_failed_json` | TEXT (JSON) | From `search_memory_service.get_search_execution()` |
| `event_count` | INTEGER | Total `monitoring_events` rows this run produced, including lifecycle events |
| `notes` | TEXT, nullable | e.g. a `max_provider_failures` policy breach |

### `monitoring_events` — new (v2.5 Step 14, live)

Append-only — "Never overwrite events" (the mission's own words) — except
`acknowledged`, the one current-state flag this row ever has updated
(`acknowledge_event()`).

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `event_id` | TEXT, `UNIQUE`, `NOT NULL` | A real UUID |
| `monitoring_run_id` | TEXT FK → `monitoring_runs.monitoring_run_id` | — |
| `saved_search_id` | TEXT FK → `saved_searches.saved_search_id` | — |
| `saved_search_version` | INTEGER | — |
| `search_id` | TEXT, nullable, FK → `search_requests.id` | — |
| `apartment_id` | TEXT, nullable, FK → `apartments.id` | — |
| `platform_id` | TEXT, nullable, FK → `platforms.id` | — |
| `connector_id` | TEXT, nullable | No dedicated connectors table exists (`ConnectorRegistry` is in-memory only), so this is a plain string, not an FK |
| `event_type` | TEXT | One of `MonitoringEventType`'s 26 named values (open-ended, not an enforced enum) |
| `severity` | TEXT | `"info"` / `"warning"` / `"critical"` |
| `significance` | REAL | `[0, 1]`, deterministic — see docs/30 "Change Significance" |
| `old_value_json` / `new_value_json` | TEXT (JSON), nullable | — |
| `explanation` | TEXT | — |
| `evidence_json` | TEXT (JSON) | — |
| `detected_at` | TEXT (ISO 8601) | — |
| `dedup_key` | TEXT | `"{saved_search_id}:{subject_id}:{event_type}"` |
| `acknowledged` | INTEGER (bool) | Default `0` |
| `notification_eligible` | INTEGER (bool) | Default `1` — delivery itself is out of scope this sprint |
| `metadata_json` | TEXT (JSON) | — |

### `event_acknowledgements` — new (v2.5 Step 14, live)

Append-only audit trail of *who*/*when* acknowledged an event, kept separate
from `monitoring_events.acknowledged` (the cheap current-state lookup) so both
a fast check and a full history exist.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `event_id` | TEXT FK → `monitoring_events.event_id` | — |
| `acknowledged_at` | TEXT (ISO 8601) | — |
| `acknowledged_by` / `note` | TEXT, nullable | — |

### `monitoring_statistics` — new (v2.5 Step 14, live)

Append-only, one row per run summarizing its own computed aggregates — this
sprint's whole "Knowledge Engine Integration" answer for monitoring-specific
metrics (see docs/30).

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `monitoring_run_id` | TEXT FK → `monitoring_runs.monitoring_run_id` | — |
| `computed_at` | TEXT (ISO 8601) | — |
| `statistics_json` | TEXT (JSON) | `MonitoringStatistics.as_dict()` — event counts by type, suppressed-duplicate count, platform success/failure counts, average significance |

### `report_artifacts` — new (v2.5 Step 14, live)

Append-only, one row per generated report file.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `monitoring_run_id` | TEXT FK → `monitoring_runs.monitoring_run_id` | — |
| `report_type` | TEXT | One of `full_html` / `full_json` / `changes_html` / `changes_json` |
| `path` | TEXT | — |
| `generated_at` | TEXT (ISO 8601) | — |

### `notification_preferences` — new (v2.5 Step 15, live)

One *current-state* row per preference — mutable, like `saved_searches`, but
the actual preference definition never changes in place; see
`notification_preference_versions` below. `update_preference_metadata()`
refreshes `enabled`/`updated_at`/`current_version` only.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `preference_id` | TEXT, `UNIQUE`, `NOT NULL` | A real UUID |
| `profile_id` | TEXT, `NOT NULL` | Feedback profile this preference belongs to |
| `saved_search_id` | TEXT, nullable, FK → `saved_searches.saved_search_id` | `NULL` = applies to every saved search for this profile |
| `current_version` | INTEGER | Points at the `notification_preference_versions` row in effect |
| `enabled` | INTEGER (bool) | Disabled preferences never match an event |
| `created_at` / `updated_at` | TEXT (ISO 8601) | `created_at` never changes after insert |

### `notification_preference_versions` — new (v2.5 Step 15, live)

Append-only: "Never overwrite preferences. Every change creates a new
immutable NotificationPreferenceVersion" (the mission's own words) — one
immutable row per edit, `UNIQUE (preference_id, version)`.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `preference_id` | TEXT FK → `notification_preferences.preference_id` | — |
| `version` | INTEGER | 1, 2, 3, ... per preference |
| `enabled_channels_json` | TEXT (JSON) | e.g. `["console", "file"]` |
| `event_types_json` | TEXT (JSON) | Empty = every event type eligible |
| `immediate_event_types_json` / `digest_event_types_json` | TEXT (JSON) | Never hardcoded — configurable per preference |
| `minimum_severity` / `minimum_significance` | TEXT nullable / REAL | Content-based eligibility thresholds |
| `digest_frequency` | TEXT, nullable | `"hourly"` / `"daily"` / `"weekly"` / `"manual"` / `NULL` (no digest) |
| `quiet_hours_start` / `quiet_hours_end` | TEXT (`"HH:MM"`), nullable | — |
| `timezone` | TEXT | IANA name, e.g. `"Europe/Madrid"` |
| `max_per_hour` / `max_per_day` | INTEGER, nullable | Rate limits, per channel |
| `include_images` / `include_original_urls` / `include_ranking_explanation` / `include_geo_summary` / `include_preference_explanation` / `include_report_links` | INTEGER (bool) | — |
| `language` / `format` | TEXT | `format` is `"text"` or `"html"` |
| `metadata_json` | TEXT (JSON) | — |
| `created_at` | TEXT (ISO 8601) | — |

### `notification_templates` — new (v2.5 Step 15, live)

Append-only registry snapshot — mirrors `filter_definitions`'
`sync_filter_definitions()` shape: `sync_registered_templates()` inserts a row
whenever a template name/version pair isn't already recorded.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `template_name` | TEXT | e.g. `"immediate_apartment_alert"`, `"daily_digest"`, `UNIQUE (template_name, version)` |
| `version` | INTEGER | — |
| `channel_compatibility_json` | TEXT (JSON) | Empty = every channel |
| `description` | TEXT | The template class's own docstring |
| `registered_at` | TEXT (ISO 8601) | — |

### `notification_batches` — new (v2.5 Step 15, live)

One current-state row per `process_pending_deliveries()` / `process_due_digests()`
/ `retry_due_failures()` call. `update_batch()` fills in `completed_at`/the
three outcome counters/`notes` once the run finishes.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `batch_id` | TEXT, `UNIQUE`, `NOT NULL` | A real UUID |
| `batch_type` | TEXT | `"immediate"` / `"digest"` / `"retry"` |
| `started_at` / `completed_at` | TEXT (ISO 8601), `completed_at` nullable | — |
| `deliveries_attempted` / `deliveries_succeeded` / `deliveries_failed` | INTEGER | — |
| `notes` | TEXT, nullable | — |

### `notification_deliveries` — new (v2.5 Step 15, live)

One current-state row per logical notification — mutable (`status`/
`attempt_count`/`next_attempt_at`/`acknowledged`/`notes` all update in place
via `update_delivery()`/`acknowledge_delivery()`), but never duplicated:
`idempotency_key` is stable per (preference, event) or (preference, digest
period), so a repeated delivery attempt always reuses the same row.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `delivery_id` | TEXT, `UNIQUE`, `NOT NULL` | A real UUID |
| `profile_id` | TEXT | — |
| `preference_id` | TEXT FK → `notification_preferences.preference_id` | — |
| `preference_version` | INTEGER | Which immutable version produced this delivery |
| `saved_search_id` | TEXT, nullable, FK → `saved_searches.saved_search_id` | — |
| `saved_search_version` | INTEGER, nullable | — |
| `batch_id` | TEXT, nullable, FK → `notification_batches.batch_id` | — |
| `is_digest` | INTEGER (bool) | — |
| `status` | TEXT | One of `NotificationDeliveryStatus`'s 11 values |
| `channels_json` | TEXT (JSON) | Channels this delivery is/was attempted through |
| `dedup_key` / `idempotency_key` (`UNIQUE`) | TEXT | Idempotency and dedup keying — see `docs/31` "Retry Policy" |
| `next_attempt_at` | TEXT (ISO 8601), nullable | Retry/deferral scheduling |
| `attempt_count` | INTEGER | — |
| `acknowledged` | INTEGER (bool) | Default `0` |
| `notes` | TEXT, nullable | e.g. `"Deferred: quiet hours"` / `"Suppressed: rate limit reached..."` — never a bare suppression with no explanation |
| `created_at` | TEXT (ISO 8601) | — |

### `notification_delivery_events` — new (v2.5 Step 15, live)

Append-only link table — every delivery (immediate or digest) links to its
`monitoring_events` via this table; a digest's extra fields live on
`notification_digests` (1:1 with a delivery) rather than duplicating this
link shape.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `delivery_id` | TEXT FK → `notification_deliveries.delivery_id` | — |
| `event_id` | TEXT FK → `monitoring_events.event_id` | — |

### `notification_digests` — new (v2.5 Step 15, live)

Append-only, `UNIQUE (delivery_id)` — 1:1 with the `notification_deliveries`
row it extends with digest-specific fields. Exact event membership is *not*
duplicated onto this table — `service.get_digest_for_delivery()` reads it back
from `notification_delivery_events` (filtered to this `delivery_id`), the
same single link table every delivery (immediate or digest) already uses.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `delivery_id` | TEXT, `UNIQUE`, FK → `notification_deliveries.delivery_id` | — |
| `frequency` | TEXT | `"hourly"` / `"daily"` / `"weekly"` / `"manual"` |
| `period_start` / `period_end` | TEXT (ISO 8601) | The exact window this digest summarizes |
| `generated_at` | TEXT (ISO 8601) | — |

### `notification_attempts` — new (v2.5 Step 15, live)

Append-only — one row per per-channel send attempt, never overwritten;
`attempt_number` plus `channel` distinguishes retries.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `delivery_id` | TEXT FK → `notification_deliveries.delivery_id` | — |
| `channel` | TEXT | e.g. `"console"` / `"email"` |
| `attempt_number` | INTEGER | — |
| `status` | TEXT | `"delivered"` / `"failed"` |
| `error` / `error_category` | TEXT, nullable | `error` is redacted of any configured secret before storage |
| `duration_ms` | INTEGER, nullable | — |
| `attempted_at` | TEXT (ISO 8601) | — |

### `notification_messages` — new (v2.5 Step 15, live)

Append-only — one row per rendered message actually handed to a channel's
`send()`; reproducible from `template_name`/`template_version` plus the
stored content.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `delivery_id` | TEXT FK → `notification_deliveries.delivery_id` | — |
| `channel` | TEXT | — |
| `subject` | TEXT, nullable | — |
| `body_text` | TEXT | — |
| `body_html` | TEXT, nullable | Only populated when the preference's `format` is `"html"` |
| `template_name` / `template_version` | TEXT / INTEGER | — |
| `language` | TEXT | — |
| `metadata_json` | TEXT (JSON) | `event_ids`/`original_listing_urls`/`report_links`/`attachments` all fold into this one JSON blob (plus e.g. `attempt_number`) rather than each getting its own column — `service.record_message()`'s own translation, not a separate schema per field |
| `generated_at` | TEXT (ISO 8601) | — |

### `rate_limit_observations` — new (v2.5 Step 15, live)

Append-only — one row per successful send, the raw data `rate_limiting
.is_rate_limited()` counts over a rolling hourly/daily window. Never deleted,
so old observations naturally age out of the window rather than requiring
cleanup logic.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `profile_id` | TEXT | — |
| `channel` | TEXT | — |
| `occurred_at` | TEXT (ISO 8601) | — |

### `channel_health_observations` — new (v2.5 Step 15, live)

Append-only — one row per send attempt (success or failure), the raw data
`service.compute_channel_health()` summarizes into a `NotificationHealth`
snapshot for the CLI's `channel-health` command.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `channel` | TEXT | — |
| `succeeded` | INTEGER (bool) | — |
| `error` | TEXT, nullable | Redacted of any configured secret |
| `duration_ms` | INTEGER, nullable | — |
| `observed_at` | TEXT (ISO 8601) | — |

### `notification_acknowledgements` — new (v2.5 Step 15, live)

Append-only audit trail of *who*/*when* acknowledged a delivery, kept
separate from `notification_deliveries.acknowledged` (the cheap current-state
lookup) — same "fast flag + full history" split `event_acknowledgements`
already established for monitoring.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | — |
| `delivery_id` | TEXT FK → `notification_deliveries.delivery_id` | — |
| `acknowledged_at` | TEXT (ISO 8601) | — |
| `acknowledged_by` / `note` | TEXT, nullable | — |

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

discovery_runs 1──* platform_candidates *──1 platforms (matched_platform_id, nullable)  (NEW)
   │                        │ 1──* platform_evidence
   │                        │ 1──* platform_verification_observations
   │                        │ 1──* platform_capability_estimates
   │                        │ 1──* platform_duplicate_links (self-referential: candidate_id / duplicate_of_candidate_id)
   │
   1──* discovery_provider_observations   (NEW, v2.5 Step 13)

saved_searches 1──* saved_search_versions
   │                1──* monitoring_schedules (1:1, saved_search_id UNIQUE)   (NEW, v2.5 Step 14)
   1──* monitoring_runs *──1 search_requests (search_id, nullable)
          │           1──* monitoring_events *──1 apartments/platforms (nullable)
          │                       │ 1──* event_acknowledgements
          │           1──* monitoring_statistics
          │           1──* report_artifacts

notification_preferences 1──* notification_preference_versions   (NEW, v2.5 Step 15)
   │              *──1 saved_searches (saved_search_id, nullable)
   1──* notification_deliveries *──1 notification_batches (batch_id, nullable)
          │               │ *──1 saved_searches (saved_search_id, nullable)
          │               │ 1──* notification_delivery_events *──1 monitoring_events
          │               │ 1──1 notification_digests (delivery_id UNIQUE)
          │               │ 1──* notification_attempts
          │               │ 1──* notification_messages
          │               │ 1──* notification_acknowledgements
          │
notification_templates — standalone registry snapshot, not FK-linked   (NEW)
rate_limit_observations / channel_health_observations — standalone, keyed by profile_id/channel   (NEW)
```

## Storage Format Outside SQLite

Unchanged from v1.1 (see [02_Folder_Guide.md](02_Folder_Guide.md)): `media/` and
`raw_pages/` remain file-based; `data/apartments/`, `search_history/`,
`platform_registry/` remain superseded/legacy; `cache/` remains outside the database. New
in v2.0: `thumbnail_path` (on `apartment_images`) points into `data/media/` alongside the
full-size image, not a new top-level folder.

## Open Questions

- Exact `status` vocabulary for `apartment_availability_history` / `current_status` (carried over from v1.1, still open).
- See [../notes/Questions.md](../notes/Questions.md) for what's still open elsewhere.
