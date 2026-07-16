# 30 — Continuous Monitoring & Saved Search Engine

Version 2.5 Step 14. Turns the platform from a one-time research tool into a
repeatable monitoring system: save a reusable search, re-run it manually or on
a schedule, compare each run with the last, and generate structured events for
whatever genuinely changed. It is **not** about email/SMS/Slack/push delivery,
a web dashboard, or autonomous connector generation — those stay out of scope
this sprint.

## Architecture

`src/monitoring/` builds entirely on top of existing engines via their already
-public APIs — none of them change to support this:

```
MonitoringEngine.run_now(db, saved_search_id)  /  .run_due(db)
        │
        ├─ 1.  service.get_saved_search() / get_saved_search_version()      (load + resolve immutable version)
        ├─ 2.  scheduling.claim_due_run() (run_due only — run_now needs no claim)
        ├─ 3.  _resolve_allowed_platforms()                                  (platform_registry, connector-available only)
        ├─ 4.  _refresh_discovery()  (optional — AutomaticDiscoveryAgent.run())
        ├─ 5.  RentalResearchAgent(db, allowed_platform_ids=...).run()       (updates Apartment History/Search Memory/Knowledge Engine internally)
        ├─ 6.  search_memory_service.compare_searches()                     (reused, not reimplemented)
        ├─ 7-9. MonitoringRegistry.all() → detector.detect(context)          (event generation)
        ├─    deduplication.is_duplicate() (central suppression pass)
        ├─ 10. report.generate_reports()                                    (full + change-only, HTML + JSON)
        └─ 11. service.update_run() / statistics.compute_statistics()       (store run + statistics)
        │
        ▼
MonitoringRun (COMPLETED / PARTIAL / FAILED) + MonitoringEvent rows
```

Every heavy engine — `RentalResearchAgent`, `FilterEngine`, `GeographicEngine`,
`RankingEngineV2`, `FeedbackEngine`, `AutomaticDiscoveryAgent` — is constructed
and called exactly as any other caller would; `MonitoringEngine` only adds
comparison, significance scoring, and event generation on top.

## Why Monitoring Is Separate From Normal Search

A normal search is one-shot: run providers, rank, write one report. Monitoring
is repeatable and stateful — it needs a comparison baseline, a safe way for an
external scheduler to re-trigger it without duplicating work, and a different
output (events describing *change*). Keeping the two separate means
`RentalResearchAgent` never needs to know about saved-search identity,
versioning, or scheduling claims; `MonitoringEngine` reuses it as a black box.

## Saved Search Lifecycle

A `SavedSearch` (`saved_searches` table) is a *current-state* row — mutable,
like `platforms`/`platform_candidates` — but its actual definition never
changes in place. Every field the mission names
(`request`/`active_filters`/`selected_platforms`/`selected_connectors`/
`geographic_destinations`/`monitoring_policy`/`report_options`/
`retention_policy`/`tags`/`metadata`/`ranking_profile`/`feedback_mode`) lives on
`SavedSearchVersion` (`saved_search_versions`, append-only). `current_version`
on `SavedSearch` points at the version actually in effect;
`MonitoringEngine.update_saved_search()` always inserts a *new* version and
bumps the pointer — "Never overwrite a saved search definition" (the mission's
own words). A prior version stays fully reproducible: it's exactly what one
`MonitoringEngine._execute()` call for that version would replay.

`active_filters` maps to `FilterConfiguration(enabled_filter_keys,
strict_validation)` — which registered filter *keys* are candidates at all —
not the actual criteria values, which live in `request["criteria"]` (the same
shape `SearchRequest.to_criteria_json()` already uses). `ranking_profile` is an
optional `{"name", "description", "weights": {...}}` dict reconstructed into a
real `RankingProfile`/`RankingWeights` at run time.

## Why Saved Searches Need Immutable Versions

A `MonitoringRun` must stay auditable: given a run, you must be able to say
exactly which criteria/filters/platforms produced it — even after the saved
search is later edited. Mutating in place would make historical runs'
provenance ambiguous and make cross-run comparison meaningless (comparing
today's run against one made under different criteria). Same discipline
`PreferenceAdjustment`/`DiscoveryRun`/`Platform` history already use elsewhere
in this codebase.

## Monitoring Workflow

The mission's own 12-step diagram, followed exactly by
`MonitoringEngine._execute()`: load saved search → resolve immutable version →
check monitoring policy → load approved active platforms → optionally refresh
platform discovery → execute Research Agent → (Apartment History / Search
Memory / Knowledge Engine already updated inline by `RentalResearchAgent.run()`
itself) → run Geographic Intelligence / Ranking Engine V2 (opt-in, wired the
same way `RentalResearchAgent` already supports) → compare with previous
monitoring run → generate structured `MonitoringEvent`s → generate HTML/JSON
reports → store `MonitoringRun` + `MonitoringStatistics`.

## Why Change Detection Relies On Historical Snapshots

"What changed" is a relationship between two points in time, not a property of
current state alone. Monitoring anchors comparison to *this saved search's*
previous `MonitoringRun` specifically (via `previous_run.search_id`), not just
"the last time any search saw this apartment" — so deltas stay scoped,
deterministic, and reproducible from stored data rather than wall-clock
timing.

## Approved Platforms And Connectors

`_resolve_allowed_platforms()` intersects `platform_registry
.list_connector_available_platforms()` (already excludes unsupported platforms
by construction) with the version's own `selected_platforms`/
`selected_connectors` allowlists and the policy's `enabled_providers`/
`disabled_providers`. The resulting id list is passed to a new, optional
`RentalResearchAgent(..., allowed_platform_ids=...)` parameter (`None` for
every pre-existing caller — unchanged behavior) which narrows, but never
expands, what `DiscoveryAgent.discover()` already permits — "select only
approved providers and certified connectors" / "Do not automatically run
unsupported platforms" (the mission's own words), satisfied at the query level,
not just informationally.

## Monitoring Policy

`MonitoringPolicy` (`models.py`) covers every field the mission names:
`manual_only`, `interval_minutes`, `daily_at` ("HH:MM"), `weekly_on`
("monday:HH:MM"), `max_runtime_seconds`, `connector_timeout_ms`,
`max_provider_failures`, `retry_policy`, `minimum_change_significance`,
`event_dedup_window_minutes`, `stale_listing_threshold`,
`removed_listing_threshold`, `rank_change_significance_threshold`,
`better_match_score_threshold`, `notification_event_types`,
`generate_reports`, `discovery_refresh_before_monitoring`,
`skip_inaccessible_platforms`, `use_cached_geo`, `force_fresh_geo`,
`enabled_providers`, `disabled_providers`. No field has a hidden universal
default a saved search can't override.

## Scheduling Interface

`src/monitoring/scheduling.py` implements the mission's own named functions —
`due_saved_searches()`, `next_run_time()`, `compute_next_run_at()`,
`claim_due_run()`, `release_run_claim()`, `mark_run_started()`/
`mark_run_completed()`/`mark_run_partial()`/`mark_run_failed()`,
`compute_health()`, `task_scheduler_command_examples()`. Nothing here loops or
sleeps — each is a single, idempotent database operation a caller invokes once
from whatever triggers it. "Do not create a background daemon tied to one
operating system" (the mission's own words): `monitoring_cli.py run-now`/
`run-due` can be invoked manually, from cron, from Windows Task Scheduler, or
from a future long-lived worker/web service — the interface doesn't care which.

`monitoring_schedules` doubles as both the "when is this due" bookkeeping and
the run-claim lock (`claimed_by`/`claim_expires_at`): claiming is one
conditional `UPDATE ... WHERE claimed_by IS NULL OR claim_expires_at < ?`,
SQLite-compatible and atomic without a separate locking mechanism — a second,
concurrent caller's `UPDATE` matches zero rows and returns `False`.

## Failure Isolation

One connector failure never aborts a monitoring run — reuses the exact pattern
already proven in `RentalResearchAgent.run()` (a failing connector is caught,
recorded, skipped) and Step 13's `AutomaticDiscoveryAgent` (a failing provider
is caught and recorded as an observation). `MonitoringRunStatus.PARTIAL`
distinguishes "some platforms genuinely failed, but others succeeded" from a
clean `COMPLETED` run or a `FAILED` one (nothing could even be attempted, or
every attempted platform failed). `platforms_attempted`/`platforms_succeeded`/
`platforms_failed` on `MonitoringRun` come from `search_memory_service
.get_search_execution()` (a small, additive public accessor this sprint added
to `search_memory_service.py` — every other read function there is scoped by
location, not by a specific search id).

## Event Model

`MonitoringEventType` is an open-ended class of string constants (mirrors
`FeedbackEventType`'s own "extensible by convention" shape) covering the
mission's 26 named types. Every `MonitoringEvent` carries `event_id`,
`saved_search_id`, `saved_search_version`, `monitoring_run_id`, `search_id`,
`apartment_id`/`platform_id`/`connector_id` (where applicable), `event_type`,
`severity`, `significance`, `old_value`/`new_value`, `explanation`,
`evidence`, `detected_at`, `dedup_key`, `acknowledged`,
`notification_eligible`, `metadata`. Events are strictly append-only —
`acknowledged` is the one current-state field this otherwise-immutable row
ever has updated (mirrors `platform_candidates.status`'s own "current-state
field on an otherwise mostly-immutable row" shape); `event_acknowledgements` is
the separate, genuinely append-only audit trail of *who*/*when* acknowledged.

## Event Detectors

`EventDetector` (ABC, `base_detector.py`) mirrors `DiscoveryProvider`'s exact
self-registration shape: `metadata()` + `detect(context) ->
list[MonitoringEvent]`, registered as instances via
`register_event_detector()`. Five ship this sprint, each reading a shared
`MonitoringDetectionContext` (already-computed evidence — a `SearchComparison`,
both runs' `search_results`, prior observed-apartment-id sets, an optional
`DiscoveryComparison` — never a live query the detector has to know how to
write itself):

- **`apartment_change`** — `NEW_MATCH`/`NEW_LISTING` (distinguished by whether
  `Apartment.first_seen_at == last_seen_at`), `PRICE_DECREASED`/
  `PRICE_INCREASED`, `AVAILABILITY_CHANGED`/`BECAME_AVAILABLE`/
  `NO_LONGER_AVAILABLE`, `LISTING_UPDATED`/`IMAGES_CHANGED`/
  `DESCRIPTION_CHANGED` (via `history_service.change_timeline()`, filtered to
  this run's `search_id` — reused, not reimplemented), `LISTING_REMOVED`/
  `LISTING_RETURNED`/`AVAILABILITY_CONFIRMED` (the removal state machine — see
  below).
- **`ranking_change`** — `RANK_INCREASED`/`RANK_DECREASED` (diffing two runs'
  persisted `search_results` rows directly) and `BETTER_MATCH_FOUND` (a new
  #1 result exceeding the previous #1's score by
  `policy.better_match_score_threshold`).
- **`filter_match`** — `FILTER_MATCH_GAINED`/`FILTER_MATCH_LOST` for an
  *existing* apartment (not brand-new, not removed) entering/leaving the
  persisted `search_results` set.
- **`platform_health`** — `CONNECTOR_FAILURE`/`CONNECTOR_RECOVERED`, diffing
  this run's `platforms_failed` against the previous run's.
- **`discovery`** — `DISCOVERY_FOUND_NEW_PLATFORM`/`PLATFORM_BECAME_ACCESSIBLE`,
  a no-op whenever `discovery_refresh_before_monitoring` wasn't requested this
  cycle.

Run-lifecycle events (`MONITORING_RUN_COMPLETED`/`_PARTIAL`/`_FAILED`,
`REPORT_GENERATED`) are emitted directly by `MonitoringEngine` itself, not by a
detector — they describe the run's own outcome, not a comparison result.

### Adding a new event type / detector

1. Add a string constant to `MonitoringEventType` (or reuse an existing one).
2. Subclass `EventDetector`, set a class-level `detector_id`, implement
   `metadata()`/`detect(context)`.
3. Call `register_event_detector(YourDetector())` at module level, and import
   that module from `detectors/__init__.py`.

No change to `MonitoringEngine`/`MonitoringRegistry` is required —
`tests/monitoring/test_registry.py` proves this directly.

## Change Significance

`significance.py` — deterministic scoring, never an ML model, every threshold
configurable via `MonitoringPolicy` rather than hardcoded: price-change
significance is the fractional price delta (capped at 1.0); availability
significance is higher for a genuine available/unavailable flip than a same-
bucket status-text change; a brand-new listing scores higher than an existing
apartment newly matching; rank-change significance scales with how large a
fraction of the candidate pool the movement represents; better-match
significance scales with how far past the configured threshold the score
delta lands. `severity_for_significance()` buckets the resulting `[0, 1]`
score into `info`/`warning`/`critical`.

## Event Deduplication

`deduplication.py` — `make_dedup_key(saved_search_id, subject_id, event_type)`
plus `is_duplicate(conn, dedup_key, new_value, policy, now)`, checked centrally
by `MonitoringEngine` after every detector has run (not inside each detector),
so suppression logic exists in exactly one place. A candidate event is
suppressed only when the *most recent* prior event under the same key reported
the same `new_value` within `policy.event_dedup_window_minutes` — a genuinely
new condition (different `new_value`) is never suppressed, and nothing is
deleted; the suppression count itself is recorded in `MonitoringStatistics
.suppressed_duplicate_count`.

## Listing Removal Logic

`removal.py` implements the mission's own three-stage state machine —
`present` → `missing` → `possibly_removed` → `confirmed_removed` — gated by
`policy.stale_listing_threshold`/`removed_listing_threshold`.
`consecutive_absences()` takes an already-fetched, newest-first list of
observed-apartment-id sets (one per prior monitoring run for this saved
search, batched once by `MonitoringEngine` rather than queried per apartment —
"Batch apartment comparisons where possible," the mission's own words) and
counts backward until the first run where the apartment was present.
`LISTING_REMOVED` fires only on the exact run where the consecutive-miss count
equals `removed_listing_threshold` (`just_crossed_removal_threshold()`) — never
on every subsequent run it stays missing. `LISTING_RETURNED` (plus
`AVAILABILITY_CONFIRMED` when the returned listing is available) takes
precedence over a generic `NEW_MATCH` for an apartment that reappears after
being missing for at least one prior run.

## Ranking Integration

`ranking_change` stores `previous_rank`/`current_rank`/`rank_delta`/
`previous_score`/`current_score`/`score_delta` per apartment
(`RankChange`, `models.py`) by diffing two runs' own persisted
`search_results` rows — no separate ranking-snapshot table needed.
`monitoring-cli compare-runs`/`statistics.compare_monitoring_runs()` exposes
the same diff directly for any two historical runs, not just consecutive ones.

## Knowledge Engine Integration

Rather than a second, parallel knowledge store, `RentalResearchAgent.run()`
already records ordinary per-platform `knowledge_service
.record_platform_observation()` calls on every monitoring cycle (reused
unchanged). What's genuinely new for monitoring's own metrics (event counts by
type, suppressed-duplicate rate, platform success/failure counts, average
significance) is captured by `monitoring_statistics` — one append-only row per
run, computed once by `statistics.compute_statistics()` — the same "plain
average/count/ratio over already-stored data" discipline `knowledge_service.py`
already established, applied to monitoring runs instead of connector
performance.

## Feedback Engine Integration

`feedback_integration.record_user_reaction()` is the *only* path from a
`MonitoringEvent` to a `FeedbackEvent`, and it is never called automatically by
`MonitoringEngine.run_now()`/`run_due()` — "Do not infer user preference merely
because an event was generated" (the mission's own words). Only an explicit,
named reaction (`saved`/`ignored`/`opened_original`/`rejected`, mapped to the
existing `FeedbackEventType` constants) produces feedback evidence, triggered
via `monitoring-cli acknowledge-event --reaction ... --profile-id ...`.

## Reporting

`report.py` writes four artifacts per run — `<run_id>_monitoring_full.{html,
json}` and `<run_id>_monitoring_changes.{html,json}` — mirroring
`discovery/automatic/report.py`'s own "plain string templating, reproducible
from stored data alone" shape. "Change-only" is exactly the full report with
the four run-lifecycle event types filtered out; everything else already *is*
a detected change, so nothing is recomputed twice. Each report includes: saved
search name/version, execution status, platforms attempted/succeeded/failed,
every event (type, severity, significance, explanation, old/new value,
evidence, apartment title/URL/images where applicable), and the generation
timestamp. Report file paths are persisted to `report_artifacts` so a report
never needs regenerating to be located later.

## CLI

`src/ui/monitoring_cli.py` (a fourth, thin entry point alongside `ui/cli.py`/
`ui/feedback_cli.py`/`ui/discovery_cli.py`): `create-saved-search`,
`list-saved-searches`, `view-saved-search`, `update-saved-search` (creates a
new version), `enable-saved-search`/`disable-saved-search`, `run-now`,
`run-due`, `list-runs`, `compare-runs`, `list-events` (filterable by
`--event-type`/`--severity`), `acknowledge-event` (optionally with
`--reaction`/`--profile-id`), `export-events`, `next-run`, `health`,
`task-scheduler-examples`.

## Task Scheduler / Cron Integration Examples

`scheduling.task_scheduler_command_examples(saved_search_id, db_path)` returns
plain command strings — never executed by this codebase itself:

```
cron:                  */15 * * * * cd /path/to/project && python -m src.ui.monitoring_cli run-now --saved-search-id <id>
windows_task_scheduler: schtasks /create /tn "Monitor <id>" /tr "python -m src.ui.monitoring_cli run-now --saved-search-id <id>" /sc minute /mo 15
manual_cli:             python -m src.ui.monitoring_cli run-now --saved-search-id <id>
```

`monitoring_cli.py`, like every other CLI in this project, always opens
`src.core.config.DB_PATH` — there is no `--db-path` override flag, so the
examples don't invent one.

## Compliance Boundaries

Monitoring obeys the exact same rules as normal research and discovery: no
CAPTCHA bypass, no authentication bypass, no anti-bot evasion, no identity
spoofing, no rate-limit violation, no repeated hammering of an inaccessible
platform. `_resolve_allowed_platforms()` only ever selects from
`connector_available` platforms (already excludes unsupported ones by
construction); `policy.skip_inaccessible_platforms` is honored by the same
mechanism, since a platform lacking a working connector was never a candidate
to begin with.

## Database

Migration `0009_continuous_monitoring.sql` — 9 new tables, every prior
migration (0001–0008) completely untouched: `saved_searches`/
`monitoring_schedules` (current-state, mutable, mirroring `platforms`/
`platform_candidates`), `saved_search_versions` (append-only, one immutable
row per edit), `monitoring_runs` (append-only header + one `update_run_status`
finalize function), `monitoring_events` (append-only + one `acknowledge_event`
flag flip), `event_acknowledgements`/`monitoring_statistics`/
`report_artifacts` (strictly append-only). See [03_Data_Model.md](03_Data_Model.md)
for the full column-by-column reference.

## Known SQLite Limitations

- **`GeoCache` has no cross-process persistence.** `MonitoringEngine` shares
  one `GeographicEngine`/`GeoCache` instance across every `_execute()` call it
  makes in its own lifetime (real, working reuse *within* one `run_due()`
  batch or one long-lived process), but a fresh CLI invocation always starts
  cold regardless of `policy.use_cached_geo` — there is no persisted geo cache
  to draw from across separate OS processes. `geo_enrichment_history` is an
  append-only log, not a substitute cache.
- **Removal-threshold tracking walks prior runs in Python, not SQL.**
  `consecutive_absences()` is O(threshold) per apartment, batched once per run
  rather than per apartment — fine at the scale a single saved search's
  history reaches, but not a windowed SQL aggregate.
- **The atomic claim lock relies on SQLite's single-writer semantics.** SQLite
  serializes writers at the database-file level, which is what makes
  `claim_due_run()`'s conditional `UPDATE` race-free for this project's
  single-database deployment; a multi-database or heavily sharded deployment
  would need a different locking primitive.
- **`--max-provider-failures` is observational, not enforcing.** A run whose
  failure count exceeds `policy.max_provider_failures` is noted in
  `MonitoringRun.notes`, but `RentalResearchAgent.run()` has no early-abort
  hook — every platform in `allowed_platform_ids` is still attempted.

## What's Deliberately Not Built This Sprint

Per the mission's own explicit instructions: email/SMS/Slack/push delivery, a
web dashboard, autonomous connector generation. See
[../notes/Questions.md](../notes/Questions.md) for the open product decisions
this leaves (which delivery channel(s) to build first, whether
`geographic_destinations` needs a richer structured shape than "a list of
`{country, region, city}` dicts," and default `MonitoringPolicy` values for a
production deployment).
