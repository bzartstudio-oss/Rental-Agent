# Changelog

All notable changes to this project. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/) — dates are when the change was made,
not a formal release date (this project doesn't cut releases yet).

## [2.5.0-rc1] — 2026-07-17 — Release Candidate Acceptance

The Release Candidate Acceptance sprint: no new product features — this
release verifies, stabilizes, documents, and packages every prior sprint
(V1.0 through Step 16) into an installable, testable, backup-able whole for
real user testing. Branch: `release/v2.5-rc1` (not merged to `main`/
`platform-v1`).

### Added
- `tests/acceptance/` — six deterministic, real end-to-end user-journey test
  suites (new search, repeat search/history, saved search/monitoring,
  notifications, feedback/ranking, discovery), each driving the real Flask
  app object or the real engines directly.
- `scripts/backup.py`, `scripts/restore.py`, `scripts/verify_backup.py` —
  timestamped, checksummed, optionally-compressed local backups (SQLite's
  own online backup API, raw pages, media, reports, non-secret config);
  restore requires an explicit destination, refuses to overwrite a
  non-empty one without `--force`, and integrity-checks the restored
  database automatically. Never includes `.env`/`.web_secret_key`/channel
  credentials.
- `scripts/health_check.py` — 13-check local installation health check
  (Python version, dependencies, Playwright, configuration, writable data
  directories, database, migrations, web binding, connector/provider/
  geographic-provider/notification-channel registries, disk space).
- `scripts/start_web.ps1` — Windows PowerShell startup convenience script.
- `docs/33_Release_Candidate_Acceptance.md`, `docs/34_Security_Acceptance.md`,
  `docs/35_Installation_and_Operations.md`, `docs/36_Performance_Baseline.md`.
- `MASTER_SPEC.md` — a single, generated-from-reality reference covering the
  entire platform's architecture, every engine, every extension point, and
  the new-developer onboarding checklist.
- `RELEASE_NOTES_v2.5-rc1.md`, `VERSION` file.
- Expanded `.env.example` with every real environment variable this
  codebase actually reads (previously only documented `OPENAI_API_KEY`).

### Fixed
- `tests/storage/test_database_migrations.py` — 4 tests had a hardcoded
  `[1..10]` migration-version list that needed extending to `[1..11]` after
  Step 16's migration; stale, not a regression.

### Removed
- **`pandas`, `numpy`, `reportlab`, `python-docx`** — verified unused (never
  imported anywhere in `src/`, not a transitive dependency of anything else
  in `requirements.txt`) and confirmed safe by re-running the complete test
  suite after uninstalling them. Likely leftover from early exploration of a
  PDF report generator, a path this project explicitly decided against
  (HTML/JSON only — see docs/09_Report_System.md).

### Explicitly Not Done This Sprint
- No new product features, no architecture redesign, no speculative
  abstractions — see docs/33's "Known Gaps" for pre-existing, honestly
  documented (not newly introduced) limitations surfaced by this
  acceptance sprint's own testing.

## [2.5.8] — 2026-07-16 — Web Dashboard and API

The first non-CLI interface: a local, server-rendered Flask web application
and a versioned JSON API (`/api/v1/`) over every engine through Step 15.
`src/web/` contains no business logic — every route calls one
`WebServiceFacade`, which calls the exact same engines the CLI already uses.

### Added
- `src/web/` — `WebApplication` (`create_app()` factory), `WebConfiguration`
  (host/port/debug/secret key, localhost-only by default), `WebDependencies`
  (constructs every engine instance once per process), `WebServiceFacade`
  (the single call surface every route/API endpoint uses), `WebErrorHandler`
  (consistent HTML/JSON errors, no raw tracebacks), `WebSecurity` (CSRF,
  security headers, path-traversal-safe `safe_join()`, `is_safe_url()`),
  `WebHealth`/`WebStatistics` (dashboard/health aggregation).
- `src/web/jobs/` — `Job`/`JobRunner`: a local, thread-based background job
  runner (no Redis/Celery) with a persisted `web_jobs` row surviving a page
  refresh or server restart; statuses `pending`/`running`/`completed`/
  `partial`/`failed`/`cancelled`.
- `src/web/forms/` — request validation (path traversal, negative prices,
  impossible ranges, unsafe URLs, excessive limits, unknown enum values) for
  search/saved-search/feedback/discovery/notification forms; the dynamic
  filter section is generated entirely from `FilterRegistry.all()`.
- `src/web/presenters/` — `to_jsonable()` (one dataclass/enum/datetime → JSON
  converter used across the whole API), apartment-card/detail presentation
  with honest confirmed/estimated/inferred/unavailable labeling.
- `src/web/routes/` + `templates/` — dashboard, new-search workflow + job
  progress + results, apartment detail, 2-5 apartment comparison, saved
  searches (create/version/enable/disable/run-now/compare-runs), monitoring
  (event list/acknowledge, manual run trigger, no OS scheduler), notifications
  (preferences/channel status/deliveries/digests/retries), discovery (manual
  run/candidate review/approve/reject), feedback (record/profile/explain/
  undo/reset), system health.
- `src/web/api/` — `/api/v1/` JSON endpoints for searches/search-jobs,
  apartments, saved searches, monitoring events, notifications, feedback, the
  learned preference profile, discovery runs/candidates, platforms, health —
  the same facade, structured JSON errors.
- Migration `0011_web_dashboard.sql` — 4 tables: `web_jobs`,
  `web_ui_preferences`, `web_saved_comparisons`, `web_recent_views`.
- One additive field on `core/agent.py::SearchRunResult`
  (`ranking_v2_results: list[RankedApartmentV2] | None = None`) so the web
  layer can show a real ranking explanation without re-running
  `RankingEngineV2` a second time — every existing caller unaffected.
- 99 new tests (1285 total).

### Security
- Session-based CSRF on every state-changing HTML request (API exempt, still
  localhost-only by default); standard hardening headers
  (`X-Content-Type-Options`/`X-Frame-Options`/`Referrer-Policy`/
  `Content-Security-Policy`/`Permissions-Policy`); path-traversal-safe id and
  file-path handling; `http`/`https`-only URL validation; a 5 MiB
  request-size limit; localhost-only binding by default, requiring an
  explicit `WEB_ALLOW_NETWORK=1` to widen.

### Explicitly not duplicated
- No ranking/filtering/monitoring-significance/notification-eligibility
  logic lives in `src/web/` — every decision is reused from the engine that
  already owns it.
- No SQL in any route — all data access goes through `WebServiceFacade` (and,
  beneath it, existing repository functions or the small `web_repository.py`
  added for this sprint's own 4 tables).

### Explicitly not built
- No mobile application, no multi-tenant billing, no autonomous connector
  generation, no real task queue (Celery/Redis — the `JobRunner` seam is
  ready for one), no full multi-user identity system, no OS-level scheduler
  inside the web server, no replacement of the existing CLI.

## [2.5.7] — 2026-07-16 — Notification Delivery Engine

Monitoring detects change and creates events; this sprint separately decides
whether/how/when an eligible event reaches a human, through whichever channels
they configured. Not SMS/mobile push, not a web dashboard, not autonomous/
marketing messaging. Monitoring and delivery stay completely separate:
`src/notifications/` never imports `MonitoringEngine`, and a notification
failure never fails, retries, or blocks a monitoring run.

### Added
- `src/notifications/` — `NotificationEngine` (preference lifecycle + the
  full delivery workflow: load undelivered eligible events, resolve preference
  version, evaluate eligibility, apply quiet hours/rate limits, choose
  immediate-or-digest, render a template, attempt delivery per channel
  independently, record attempts, update status/statistics),
  `NotificationChannelRegistry`/`NotificationChannel` and
  `NotificationTemplateRegistry`/`NotificationTemplate` (self-registering
  plugin systems), `eligibility.py` (deterministic/explainable content-based
  checks), `quiet_hours.py`/`rate_limiting.py` (timezone-aware deferral/
  suppression), `retry.py` (idempotent exponential backoff + dead-lettering),
  `scheduling.py` (database-backed due-time interface), `statistics.py`,
  `feedback_integration.py` (explicit-reaction-only bridge to the Feedback
  Engine).
- Four built-in channels: `console`/`file` (always enabled, zero
  credentials), `email` (provider-independent SMTP, disabled until
  `smtp_host`/`sender_address` are configured), `webhook` (generic HTTP POST
  with HMAC signing and domain allow/deny lists, disabled until a valid `url`
  is configured).
- Eight built-in templates: 6 immediate alert templates
  (`immediate_apartment_alert`/`price_change_alert`/`availability_alert`/
  `better_match_alert`/`listing_removal_alert`/`monitoring_failure_alert`)
  and 2 digest templates (`daily_digest`/`weekly_digest`).
- Immutable preference versioning: `NotificationPreference` (current-state
  row) + `NotificationPreferenceVersion` (append-only) — every edit creates a
  new version, prior versions stay fully reproducible.
- Migration `0010_notification_delivery.sql` — 12 tables
  (`notification_preferences`, `notification_preference_versions`,
  `notification_templates`, `notification_batches`, `notification_deliveries`,
  `notification_delivery_events`, `notification_digests`,
  `notification_attempts`, `notification_messages`,
  `rate_limit_observations`, `channel_health_observations`,
  `notification_acknowledgements`). `0001`–`0009` untouched.
- `src/ui/notification_cli.py` — a new, separate CLI entry point:
  `create-preference`/`list-preferences`/`view-preference`/
  `update-preference`/`enable-notifications`/`disable-notifications`/
  `preview-notification`/`send-test-notification`/`deliver-pending`/
  `generate-digest`/`retry-due`/`list-deliveries`/`list-failed-deliveries`/
  `retry-delivery`/`cancel-delivery`/`acknowledge-notification`/
  `channel-health`/`statistics`/`export-history`/`task-scheduler-examples`.
- `docs/31_Notification_Delivery.md`.
- 156 new tests (1186 total).

### Fixed
- `EmailNotificationChannel.send()`'s except-clause ordering: `smtplib
  .SMTPException` subclasses `OSError` in this Python version, so a plain
  `except (..., OSError)` clause placed before `except SMTPException`
  swallowed every generic SMTP protocol error and miscategorized it as
  `"connection_error"` instead of `"server_error"` — the `"server_error"`
  branch was unreachable. Fixed by reordering except clauses most-specific-
  first. Caught by a new test before this ever ran against a real mail
  server.
- `notifications.service.get_due_retries()` originally selected only
  `status = 'retry_scheduled'` deliveries, missing `partially_delivered`
  deliveries that still have failed channels worth retrying — one channel
  failure not blocking another applies symmetrically to retries.

### Explicitly not duplicated / not built this sprint
- `NotificationEngine` consumes `MonitoringEvent`s exclusively through
  `monitoring.service`'s public read functions — never `MonitoringEngine`
  internals, never a write to any `monitoring_*` table.
- Templates link to already-generated monitoring report files and to the
  apartment's own URL/images — never a second report-generation
  implementation.
- SMS, mobile push, a web dashboard, and autonomous outbound/marketing
  messaging are explicitly out of scope this sprint, per the mission's own
  instructions. Future channels (Slack/Teams/Telegram/Discord/SMS/push) are
  addable later with zero `NotificationEngine` changes, but none ship now.

## [2.5.6] — 2026-07-16 — Continuous Monitoring and Saved Search Engine

Turns the platform into a repeatable monitoring system — save a reusable search,
re-run it manually or on a schedule, compare each run with the last, generate
structured events for genuine changes. Not email/SMS/Slack/push delivery, not a
web dashboard, not autonomous connector generation.

### Added
- `src/monitoring/` — `MonitoringEngine` (saved-search lifecycle + the 12-step
  monitoring workflow), `MonitoringRegistry`/`EventDetector` (self-registering
  plugin system, 5 built-in detectors), `scheduling.py` (database-backed
  due/claim/release interface), `significance.py`/`removal.py`/`deduplication.py`
  (deterministic change scoring, the three-stage removal state machine, centralized
  event suppression), `statistics.py` (`compute_statistics()`/
  `compare_monitoring_runs()`), `feedback_integration.py` (explicit-reaction-only
  bridge to the Feedback Engine), `report.py` (full + change-only HTML/JSON
  reports).
- Five built-in event detectors: `apartment_change` (new match/listing, price,
  availability, listing detail changes, removal-threshold tracking), `ranking_change`
  (rank/score movement, better-match-found), `filter_match` (gained/lost),
  `platform_health` (connector failure/recovery), `discovery` (new platform
  candidates, connector-availability changes).
- Immutable saved-search versioning: `SavedSearch` (current-state row) +
  `SavedSearchVersion` (append-only) — every edit creates a new version, prior
  versions stay fully reproducible.
- Migration `0009_continuous_monitoring.sql` — 9 tables (`saved_searches`,
  `saved_search_versions`, `monitoring_schedules`, `monitoring_runs`,
  `monitoring_events`, `event_acknowledgements`, `monitoring_statistics`,
  `report_artifacts`). `0001`–`0008` untouched. `monitoring_schedules` doubles as
  the atomic run-claim lock.
- `src/ui/monitoring_cli.py` — a new, separate CLI entry point:
  `create-saved-search`/`list-saved-searches`/`view-saved-search`/
  `update-saved-search`/`enable-saved-search`/`disable-saved-search`/`run-now`/
  `run-due`/`list-runs`/`compare-runs`/`list-events`/`acknowledge-event`/
  `export-events`/`next-run`/`health`/`task-scheduler-examples`.
- `docs/30_Continuous_Monitoring.md`.
- 88 new tests (1030 total).

### Changed (backward compatible)
- `RentalResearchAgent.__init__` gained one optional `allowed_platform_ids: list[str]
  | None = None` parameter — `None` (every existing caller) is unchanged behavior;
  when given, narrows (never expands) which connector-available platforms `discover()`
  already permits.
- `search_memory_service.py` gained one small additive public accessor,
  `get_search_execution(conn, search_id)` — every other read function there was
  scoped by `location`, not by a specific search id.

### Explicitly not duplicated / not built this sprint
- Every heavy engine this sprint touches — `RentalResearchAgent`, `FilterEngine`,
  `GeographicEngine`, `RankingEngineV2`, `FeedbackEngine`, `AutomaticDiscoveryAgent`
  — is reused via its already-public API, unchanged.
- Notification *delivery* (email/SMS/Slack/push), a web dashboard, and autonomous
  connector generation are explicitly out of scope this sprint, per the mission's
  own instructions.
- Comparison between monitoring runs reuses `SearchComparison` (Search Memory)
  directly — never a second, parallel apartment-diffing implementation.

### Key design decision
- Event deduplication is checked centrally, once per run, after every detector has
  contributed candidate events — not inside each detector. `LISTING_REMOVED` fires
  exactly once, on the run that crosses `removed_listing_threshold`, never on every
  subsequent run a listing stays missing.

## [2.5.5] — 2026-07-16 — Automatic Platform Discovery Agent

A provider-independent system that discovers, evaluates, deduplicates, classifies,
verifies, and stores rental-platform *candidates* for a country/region/city — not
connector generation, not authentication/CAPTCHA/robots bypass. Evidence-based,
auditable, configurable, manually triggerable.

### Added
- `src/discovery/automatic/` — `AutomaticDiscoveryAgent` (the 12-step discovery
  pipeline), `DiscoveryProviderRegistry`/`DiscoveryProviderFactory` (self-registering
  plugin system), `DiscoveryProvider` (ABC), thin `service.py` storage orchestration,
  `statistics.py` (`compute_discovery_statistics()`/`compare_discovery_runs()`),
  `report.py` (HTML + JSON discovery reports).
- Deterministic classification (`classification.py`, 13 categories, keyword-scoring,
  never ML), verification (`verification.py`, injectable `PageFetcher` — a real
  `HttpPageFetcher` in production, always a fixture in tests), capability estimation
  (`capability.py`, 14 capabilities, always `is_estimate=True`), and two-tier
  deduplication (`normalization.py` — normalized domain collapses to one row;
  normalized name across a different domain links a genuine duplicate row).
- Two built-in discovery providers: `curated_seed` (surfaces
  `discovery/known_platforms.py`'s existing public facts by country) and
  `manual_url` (surfaces a request's own `manual_urls`).
- Migration `0008_automatic_platform_discovery.sql` — 7 tables (`discovery_runs`,
  `platform_candidates`, `platform_evidence`, `platform_verification_observations`,
  `platform_capability_estimates`, `platform_duplicate_links`,
  `discovery_provider_observations`). `0001`–`0007` untouched. Every table but
  `discovery_runs`/`platform_candidates` is strictly append-only.
- `src/ui/discovery_cli.py` — a new, separate CLI entry point:
  `discover`/`list-discovered`/`list-verified`/`list-unsupported`/
  `list-missing-connectors`/`compare-runs`/`approve-candidate`/`reject-candidate`/
  `view-evidence`/`view-coverage-summary`.
- `docs/29_Automatic_Platform_Discovery.md`.
- 78 new tests (942 total).

### Explicitly not duplicated / not built this sprint
- The Existing Platform Registry (`discovery/discovery_agent.py`/
  `platform_registry.py`) remains completely unchanged and canonical — this agent
  only ever contributes candidates; promotion happens exclusively through the
  existing `DiscoveryAgent.sync_platforms()` path (now reachable via
  `discovery-cli approve-candidate`).
- Connector code generation, continuous monitoring, and notifications are
  explicitly out of scope this sprint, per the mission's own instructions.
- Connector-availability checks reuse the existing `ConnectorRegistry` directly —
  never a second, parallel connector-tracking mechanism.

### Key design decision
- A discovered platform never automatically becomes research-active. Status
  assignment is one explicit, documented priority list (duplicate → inaccessible →
  requires-login → irrelevant → connector-available → connector-missing →
  requires-manual-review → verified → relevant), and only a registered connector or
  an explicit human approval can ever produce `CONNECTOR_AVAILABLE`.

## [2.5.4] — 2026-07-16 — User Feedback and Preference Learning Engine

A modular system that learns user preferences from explicit, traceable evidence —
deterministic, no machine learning, no opaque prediction, no silent ranking-rule
changes.

### Added
- `src/feedback/` — `FeedbackEngine` (record/build/explain/undo/reset/export/
  compare), `FeedbackService` (thin storage orchestration), `FeedbackRegistry`
  (self-registering plugin system), `PreferenceRule` + 4 shared aggregation bases
  (`ImportancePreferenceRule`/`ThresholdPreferenceRule`/`CategoricalPreferenceRule`/
  `BooleanPreferenceRule`), `DecayConfig`/`compute_confidence()` (centralized,
  configurable decay and confidence math).
- 23 built-in preference rules: 12 real, `Apartment`/`GeoEnrichment`-field-backed
  (price sensitivity, maximum budget, walking distance, public transport,
  availability importance, property type, minimum area, number of rooms,
  platform, neighborhood, lifestyle, nearby services) and 11 honestly dormant-
  field dimensions learned only from explicit filter choices (room type, private
  bathroom, private kitchen, air conditioning, furnished, pets, balcony, parking,
  utilities included, internet included, number of flatmates).
- `src/feedback/ranking_adapter.py` — the sole module coupling `feedback` to
  `ranking_v2`; three modes (`EXPLICIT_ONLY`/`SUGGESTED`/`ASSISTED`).
- `src/feedback/filter_integration.py` — records repeated filter choices as
  feedback without ever promoting a preference into a required filter.
- Migration `0007_feedback_and_preferences.sql` — `feedback_events` (append-
  only), `preference_observations`, `preference_adjustments`, `preference_snapshots`.
  `0001`–`0006` untouched.
- `src/ui/feedback_cli.py` — a new, separate CLI entry point:
  record/profile/explain/history/undo/reset/export.
- `docs/28_User_Feedback_and_Preference_Learning.md`.
- 130 new tests (864 total).

### Changed
- `RentalResearchAgent.__init__` gained three new, optional, default-`None`/
  `SUGGESTED` parameters (`feedback_engine`/`feedback_profile_id`/`feedback_mode`).
  Every existing caller is unaffected.
- `ui/cli.py` gained `--feedback-profile-id`/`--feedback-mode`.
- `services/report_generator.py` gained one new, optional, default-`None`
  `preference_profile` parameter, rendering explicit vs. inferred preferences
  with confidence.

### Explicitly not duplicated
- Every rule reuses an existing engine's own function (`knowledge_service.
  average_city_price()`, `GeoEnrichment`, real `Apartment` fields) — no formula
  was reimplemented. Dormant-field rules reuse `filter_engine`'s own key strings
  for the same concepts.

### Key design decision
- The preference-adjustment log, not a recomputed-every-time aggregate, is the
  source of truth for "current" values — this is what makes `undo`/`reset`
  genuinely effective: both write a new adjustment whose timestamp becomes a new
  evidence cutoff, so a manual undo/reset sticks until genuinely new events
  arrive, without ever deleting a raw feedback event.

### Privacy
- Sensitive personal characteristics (gender, ethnicity, religion, health
  status, sexual orientation, political views) are never inferred — enforced by
  a structural test, not just documentation.

## [2.5.3] — 2026-07-16 — Intelligent Ranking Engine V2

A modular, explainable, evidence-based decision engine — deterministic, no machine
learning, no opaque scoring. Every score returns Final Score, Confidence, Evidence,
Rule Contributions, Warnings, and Timestamp.

### Added
- `src/ranking_v2/` — `RankingEngineV2` (entry point), `RankingPipeline` (scoring
  core), `RankingRule`/`RankingRuleRegistry` (self-registering plugin system),
  `RankingWeights`/`RankingProfile` (user-configurable priorities, two built-in
  presets), `RankingEvidence`/`RankingExplanation`/`RankingConfidence`
  (per-apartment explainability), `RankingStatistics`.
- 12 built-in rules, one per named input (Dynamic Filters, Geographic Intelligence
  ×3, Apartment History, Knowledge Engine, Platform Reliability, Availability,
  Price History, Analysis Results, Provider Health, Connector Reliability, Search
  History) — none recompute a formula another engine already owns; each reads that
  engine's own function directly.
- `docs/27_Intelligent_Ranking_Engine.md`.
- 94 new tests (734 total).

### Changed
- `RentalResearchAgent.__init__` gained one new, optional, default-`None`
  `ranking_engine_v2` parameter. Every existing caller is unaffected.
- `ui/cli.py` gained `--use-ranking-v2` and `--ranking-profile {default,comprehensive}`.
- `services/report_generator.py` gained one new, optional, default-`None`
  `ranking_v2_results` parameter, rendering Score/Confidence/Top Positive Factors/
  Top Negative Factors per listing.

### Explicitly not duplicated
- Every rule reuses an existing engine's own read function
  (`knowledge_service.average_city_price()`/`platform_reliability()`/
  `connector_health()`, `apartment_repository.get_price_history()`,
  `GeoEnrichment`, `AnalysisResult`) — no comparison or aggregation formula was
  reimplemented.

### Key design decision
- Per-apartment weight renormalization: a rule with no evidence for a given
  apartment is excluded from both the score numerator and the weight-normalization
  denominator for that apartment, never counted as a zero — an apartment is never
  punished for missing optional context nobody asked this run to compute.

### Known, honestly-documented limitation
- `filter_results`/`provider_health`/`search_comparison` are not auto-wired by
  `core/agent.py` this sprint — all three rules remain real, registered, and
  tested, just dormant through the standard pipeline until a future sprint
  assembles that context.

## [2.5.2] — 2026-07-15 — Geographic Intelligence Engine

A modular, provider-independent engine that calculates spatial relationships between
apartments and points of interest — not a map viewer. No map/routing provider is
hardcoded; every provider implements one interface and self-registers.

### Added
- `src/geography/` — `GeographicEngine` (orchestrator), `GeoProvider`/
  `GeoProviderRegistry`/`GeoProviderFactory` (self-registering plugin system),
  `GeoCache` (the first real caching infrastructure in this codebase — closes the
  Production Readiness Review's Question 4 finding), `DistanceCalculator`/
  `TravelTimeCalculator`/`RouteCalculator`/`NearbySearch`, `GeoStatistics`,
  `GeoHistory`.
- `HaversineGeoProvider` — the one built-in provider: real straight-line distance
  (`src.analysis.geo.haversine_km`, reused), confidence `1.0`; honestly estimated
  walking/cycling/driving/public-transport travel time (distance ÷ a documented
  average speed per mode), confidence `0.4`; nearby search across all 17 mission
  categories, reusing the exact `nearby_amenities`/`knowledge_entries` convention
  `analysis/analyzers/nearby_amenity.py` already established.
- Migration `0006_geo_enrichment_history.sql` — `GeoHistory`'s persistence.
  `0001`–`0005` untouched.
- `docs/26_Geographic_Intelligence.md`.
- 78 new tests (640 total).

### Changed
- `RentalResearchAgent.__init__` gained one new, optional, default-`None` `geo_engine`
  parameter. Every existing caller is unaffected.
- `ui/cli.py` gained one new, off-by-default flag: `--use-geo-engine`.
- `services/report_generator.py` gained one new, optional, default-`None`
  `geo_enrichments` parameter, rendering walking/driving/public-transport time,
  nearby services, distance summaries, and confidence per listing.

### Explicitly not duplicated
- `HaversineGeoProvider` reuses `src.analysis.geo.haversine_km` and the exact
  `nearby_amenities` curated-data convention — no distance formula or lookup
  convention was reimplemented.

### Known, honestly-documented limitation
- No real routing/geocoding/places API is integrated — travel time for every mode
  besides straight-line is a documented average-speed estimate, not real routing.
  Three existing Analysis Engine analyzers (`walking_distance.py`,
  `public_transport.py`, `nearby_amenity.py`) compute conceptually similar facts and
  were deliberately not refactored to delegate to this engine this sprint.

## [2.5.1] — 2026-07-15 — Dynamic Filter Engine

Fulfills the Version 2.0 Step 8 slot's original intent (a filter-engine subpackage,
originally sketched as one or two example filters per category), built for real
instead as a new v2.5 step with all ~38 mission-requested filters.

### Added
- `src/filter_engine/` — a fully modular, self-registering plugin system:
  `BaseFilter`, `FilterRegistry`/`FilterFactory`, `FilterConfiguration` (enable/
  disable filters without touching the engine), `FilterContext`, composition
  (`FilterCondition`/`FilterGroup`/`FilterOperator` — AND/OR/NOT/nesting),
  `FilterValidator`, `FilterStatistics`, `FilterHistory`, `sync_filter_definitions()`
  (finally uses the `filter_definitions` table designed in migration 0001).
- 39 built-in filters: 12 data-backed (max/min price, currency, property type, exact
  room count, min/max area, image count, platform, and three Deep-Analysis-Engine-
  backed proximity filters), 27 honestly dormant (amenities, room/flatshare
  preferences, structured geography, stay duration, room type, radius — real,
  registered, tested filters for fields that don't exist in the schema yet; always
  pass, never fabricate an exclusion).
- Migration `0005_filter_execution_history.sql` — `FilterHistory`'s persistence.
  `0001`–`0004` untouched.
- `docs/25_Dynamic_Filter_Engine.md`.
- 102 new tests (562 total).

### Changed
- `search/criteria.py`'s `get_filter()`/`registered_keys()` now fall back to/include
  the Dynamic Filter Engine's registry (deferred import, no circular dependency) — a
  `SearchRequest` can now reference any of the 39 new filters, not just the original 5.
- `RentalResearchAgent.__init__` gained one new, optional, default-`None`
  `filter_engine` parameter. Every existing caller is unaffected.
- `ui/cli.py` gained one new, off-by-default flag: `--use-filter-engine`.

### Explicitly not duplicated
- Data-backed filters reuse `search.criteria.FilterDefinition`'s existing
  `max_price`/`min_price`/`min_sqft` logic and the Analysis Engine's already-computed
  proximity scores — no comparison formula was reimplemented.

### Known, honestly-documented limitation
- The three distance filters operate on the Analysis Engine's normalized `[0,1]`
  proximity score, not a literal km/minute value — that raw distance only exists as
  formatted text inside the analyzer's own evidence, never a structured field.

## [2.5.0] — 2026-07-15 — Production Provider Framework

A new version, not a Version 2.0 step — begun once Steps 1–7, the SDK Validation
Sprint, and the Production Readiness Review were all confirmed complete. Completes
the Provider Abstraction Layer (2.0.9) into a full production framework.

### Added
- `src/providers/configuration.py` — `ProviderConfiguration` (mirrors
  `ConnectorConfiguration`: `timeout_ms`/`max_retries`/`rate_limit_per_minute`/
  `credentials`).
- `src/providers/factory.py` — `ProviderFactory`, the sanctioned way to resolve a
  provider by id (thin delegation to `ProviderRegistry`).
- `src/providers/health.py` — `ProviderHealth`/`check_provider_health()`: current
  availability plus the same `ConnectorHealth` the Knowledge Engine already tracks.
- `src/providers/metrics.py` — `ProviderMetrics`/`build_provider_metrics()`/
  `record_provider_metrics()`: one run's metrics, computed via the existing
  `src.knowledge.metrics` formulas, not reimplemented.
- `src/providers/statistics.py` — `ProviderStatistics`/`provider_statistics()`: the
  aggregate reliability view, delegating to `knowledge_service.platform_reliability()`.
- `src/providers/validator.py` — `ProviderValidator`/`ProviderValidationResult` +
  `ProviderValidationError`: validates declared `ProviderMetadata` score ranges and
  surfaces (never re-derives) a data provider's connector-level validation warnings.
- `docs/24_Production_Providers.md`.
- 32 new tests (460 total).

### Changed
- `DataProvider.search()`/`AIProvider.summarize()` gained an optional, default-`None`
  `config: ProviderConfiguration` parameter on the base class and all four built-in
  providers — every existing call site is unaffected.
- `core/agent.py`'s `_run_data_router()` now builds and structured-logs a
  `ProviderMetrics` snapshot per router-selected run (no duplicate database write —
  the observation itself is still recorded exactly once, via the pre-existing
  `platform_metrics` bookkeeping).

### Explicitly not duplicated
- `ProviderRegistry`, `ProviderRouter`, and the scoring model (2.0.9) were reused as-is,
  not rebuilt, despite being named in the mission's "Create" list.
- No retry/backoff/pagination logic was reimplemented at the provider layer — every
  provider still delegates that to its connector.

## [2.0.10] — 2026-07-15 — SDK Validation Sprint

A verification exercise, not new functionality: checks four specific claims about the
Connector SDK (2.0.6) empirically.

### Added
- `src/connectors/sample_json_feed/` — a fourth reference connector (JSON, not HTML),
  built purely as a controlled experiment for this sprint. Deliberately not seeded in
  `discovery/known_platforms.py`.
- `tests/connectors/test_sample_json_feed.py` — includes `AutoDiscoveryTests`, which
  forcibly evicts the connector from the registry to prove factory auto-discovery
  goes `False` → `True` around one `ConnectorFactory.get()` call.
- `docs/22_SDK_Validation_Sprint.md` — full findings for all four questions.
- 15 new tests (428 total).

### Changed
- `services/report_generator.py` now renders platform name, listing identifier,
  property type, currency, coordinates, and last-observed timestamp per listing —
  fields `Apartment` already carried but the report never surfaced (a real gap found
  while answering "is the normalized model complete enough").

### Findings (honestly reported, not all fixed)
- **Confirmed**: a second (third, fourth) connector can be added with zero changes to
  any existing file; the factory discovers it automatically by naming convention;
  connectors are genuinely independent (import audit, standalone test runs, no shared
  mutable state beyond an additive registry).
- **Real gap, left open**: no `room_type` field exists in `RawListing`/`Apartment`,
  despite being requested by the v2.0 Step 7 mission — connects to the already-known,
  deliberately deferred room/flatshare product-scope question.
- **Real gap, left open**: no field carries a platform's own "last updated" fact,
  distinct from this system's own observation timestamps.

## [2.0.9] — 2026-07-15 — Provider Abstraction Layer

Not a numbered Version 2.0 implementation step — a separate, orthogonal capability
requested after Step 7, sitting on top of the Connector SDK (2.0.6) and RentCast
(2.0.8) rather than continuing either one's own scope.

### Added
- `src/providers/` — a common `Provider` interface (`is_available()`, `metadata()`)
  with two kinds: `DataProvider` (adds `platform_id`, `search()`) and `AIProvider`
  (adds `summarize()`).
- `ProviderRegistry` — eager self-registration (`register_provider(instance)`),
  mirroring the Analysis Engine's registry pattern.
- `scoring.py` — pure `score_provider()`: availability (hard gate, not just a
  weighted term), cost, freshness, quality combined into one score; weights are
  configurable data (`ScoringWeights`), never hardcoded.
- `ProviderRouter.run_with_fallback()` — ranks available candidates best-first, tries
  each until one succeeds (or its result reports failure), logs the full ranking and
  every attempt's outcome, raises `NoProviderAvailableError` only once every
  candidate has failed.
- Four built-in providers: `RentCastDataProvider`/`LocalDemoDataProvider` (thin
  adapters over `ConnectorFactory` — no fetching/parsing logic duplicated),
  `OllamaAIProvider` (real HTTP to a local Ollama server for summarization),
  `NullAIProvider` (always available, honestly returns `None`, never a fabricated
  summary).
- `docs/21_Provider_Abstraction_Layer.md`.
- 52 new tests (413 total): pure scoring/registry tests, router fallback tests using
  scripted fake providers, per-provider unit tests with transport mocked, and a full
  agent-level integration test (no API key → local demo; RentCast configured and
  working → preferred; RentCast failing mid-run → falls back to local demo in the
  same run; AI summary appears/omits/falls back correctly; default no-router
  behavior unaffected).

### Changed
- `RentalResearchAgent.__init__` gained two new, optional, default-`None`
  parameters: `data_router`, `ai_router`. Every existing caller is unaffected.
- `services/report_generator.py::generate_report()` gained one new, optional,
  default-`None` parameter: `ai_summary`. `None` renders no summary section.
- `ui/cli.py` gained one new, off-by-default flag: `--use-provider-router`.

### Works with zero configuration
- No `RENTCAST_API_KEY` and no local Ollama running still produces a complete
  search and report — `LocalDemoDataProvider`/`NullAIProvider` are always available,
  by design.

## [2.0.8] — 2026-07-15 — First Production Connector (RentCast)

Built as Step 7 — reassigned a second time, this time pulling forward the item
"After v2.0: Still the Same Answer" (`docs/10_Roadmap.md`) had deferred to after
Version 2.0 entirely: pick a real first platform and prove the Connector SDK (Step 5)
against it, not just the two local fixtures it had only ever been tested with. Dynamic
Filter Engine (previously Step 7) is pushed to Step 8.

### Added
- `src/connectors/rentcast/` — the first production (real, non-demo) connector:
  `connector.py` (`RentCastConnector`) and `client.py` (`RentCastClient`, retry/backoff
  HTTP transport).
- `src/utils/logging.py` — `get_logger()`/`StructuredFormatter`, the first real use of
  `logging` in this codebase.
- Migration `0004_production_connector_fields.sql` — adds `apartments.currency`/
  `.property_type` (both nullable). `0001`–`0003` untouched.
- `RawListing`/`Apartment`/`normalizer.py`/`apartment_repository.py` gained matching
  `currency`/`property_type` fields; `RawListing` also gained `latitude`/`longitude`
  (already on `Apartment` since migration 0001, never populated by any connector until
  now).
- `discovery/known_platforms.py` — RentCast added to `REFERENCE_CONNECTORS`
  (`connector_available=True`, `connector_name="rentcast"`).
- `docs/20_First_Production_Connector.md` — why RentCast, the field-mapping table,
  retry/pagination policy, limitations, and how to add the next connector. (The
  mission asked for `docs/19_...`; `19` was already taken by the Analysis Engine —
  used the next free number.)
- 47 new tests (361 total): `RentCastClient` retry/backoff/auth-failure tests,
  `RentCastConnector` normalize/parse/pagination/failure tests, full `search()`-level
  failure tests (malformed listing, missing images, missing coordinates, empty
  results, network timeout, missing API key — every one a normal failed
  `ConnectorResult`, never a raised exception), SDK certification via the existing
  `ConnectorCertificationMixin`, and a full-pipeline integration test. All HTTP calls
  mocked — no test spends real RentCast free-tier quota.

### Fixed
- `BaseConnector.search()` (Step 5): `connect()` was called *outside* its `try:`
  block — invisible until `RentCastConnector.connect()` became the first override that
  legitimately raises (`ConnectorConfigurationError` on a missing API key). Moved
  inside the guard; zero behavior change for connectors whose `connect()` never
  raises.

### Why RentCast
- A real, developer-facing REST API (`api.rentcast.io/v1`), not a scraped website —
  self-service `X-Api-Key` auth, a free tier (50 requests/month), and published Terms
  of Use permitting this kind of programmatic access, verified by live lookup before
  writing any connector code. Chosen over the 6 previously-catalogued platforms
  (Zillow, Apartments.com, Rightmove, Idealista, Fotocasa, ImmoScout24), none of which
  offer a comparable path and all of which prohibit scraping — all 6 remain
  `connector_available=False`.
- No authentication bypassed, no anti-bot/CAPTCHA protection circumvented.

### Known limitations (never fabricated, honestly reported)
- No photos/images field in RentCast's schema — `image_urls` is always `[]`.
- No description field — always `None`.
- No browsable listing page — `url` points at RentCast's own per-listing API record,
  documented as such, not a page a person could open in a browser.
- US-only coverage; free-tier quota (50 requests/month) bounds pagination to a
  conservative 100/page × 3 pages.

## [2.0.7] — 2026-07-15 — Deep Analysis Engine

Built as Step 6 (ahead of the Dynamic Filter Engine, originally planned as Step 6, now
Step 8 — see [2.0.8]) at explicit instruction — `docs/10_Roadmap.md` updated to reflect
the actual build order.

### Added
- `src/analysis/` — a self-registering analyzer plugin framework: `BaseAnalyzer`
  (thin contract: `metadata()`/`analyze()`), `AnalysisRegistry`
  (`@register_analyzer`), `AnalysisPipeline` (every analyzer, one apartment, isolating
  a broken one), `AnalysisEngine` (every apartment, one search — held by
  `core/agent.py`), `scoring.py` (configurable composite scoring — weights are data,
  never hardcoded), `analysis_service.py` (append-only write/read persistence).
- Eleven analyzers: `walking_distance`, `public_transport` (real haversine math —
  `src/analysis/geo.py`), and nine "nearby X" amenity analyzers (supermarkets,
  pharmacies, hospitals, universities, schools, parks, restaurants, gyms, parking)
  sharing one base class.
- Five composite scores: Location, Convenience, Lifestyle, Accessibility, and Overall
  Analysis Score.
- Migration `0003_analysis_engine_metrics.sql` — adds `confidence`/`evidence_json`/
  `analyzer_version` to `apartment_analysis_metrics` (schema-only since migration
  0001). `0001`/`0002` untouched.
- `docs/19_Analysis_Engine.md` — architecture, pipeline, analyzer lifecycle, how to
  build a new analyzer, scoring model. (The mission asked for `docs/18_...`; `18` was
  already taken by the Connector SDK — used the next free number.)
- 58 new tests (314 total): unit tests for every module, per-analyzer no-evidence/
  real-evidence tests, a broken-analyzer isolation test, a new
  `tests/services/test_report_generator.py`, a real-pipeline integration test, and a
  300-apartment performance test.

### Changed
- `core/agent.py`: `AnalysisEngine` runs after Apartment History, before Ranking.
  (The mission's diagram placed it after Search Memory/Knowledge Engine too, but both
  must run at the very end of `run()` by their own already-documented design — see
  `docs/19_Analysis_Engine.md` "Pipeline" for why moving them would have broken
  passing tests.)
- `services/report_generator.py::generate_report()` gained one new, optional,
  default-`None` parameter (`analysis_results`) to show analyzer/composite scores,
  evidence, and warnings per listing. Every existing caller is unaffected.

### Evidence model — no live external data source
- Every analyzer's evidence is real coordinate math (haversine) or a curated
  `storage/reference_data_repository.py` (`knowledge_entries`) fact — never a live
  geocoding/places/transit API, since that vendor decision remains genuinely unmade.
  A "no evidence" result (`score=None`) is honestly reported, never persisted, and
  visible in the report as a warning for the run that computed it.
- Verified against the real dev database: ran the CLI with no curated data (zero
  metrics persisted, correctly honest), then seeded a few illustrative `Example City`
  facts and ran again, confirming real, correctly-computed scores through to the
  report.

### Not included (explicitly out of scope)
- No real geocoding/places/transit API integration, no machine learning, no AI, no
  predictive inference anywhere — every score is deterministic arithmetic or a direct
  function of a curated fact.
- No wiring into `search/criteria.py` or `ranking/` — that's the Dynamic Filter
  Engine's job (now Step 8, not yet built); this sprint only makes the metrics exist.

## [2.0.6] — 2026-07-15 — Connector SDK & Plugin Framework

The largest sprint of Version 2.0 — a full plugin framework for connectors, not just
the originally-sketched template method.

### Added
- `src/connectors/sdk/` — the Connector SDK: `BaseConnector` (template method:
  `connect -> fetch_listing -> parse -> normalize -> validate -> ConnectorResult`),
  `ConnectorFactory` (the only sanctioned way to obtain a connector — `core/agent.py`
  never imports/instantiates one directly), `ConnectorRegistry` (self-registration via
  `@register_connector`), `ConnectorMetadata`/`ConnectorCapabilities` (declarative
  coverage + capability discovery), `ConnectorConfiguration`, `ConnectorValidator`
  (structured, non-fatal-by-default field-completeness warnings), and a
  `ConnectorException` hierarchy (`ConnectorConnectionError`, `ConnectorParsingError`,
  `ConnectorValidationError`, `ConnectorConfigurationError`).
- `docs/18_Connector_SDK.md` — architecture, lifecycle, how to build a new connector,
  best practices, certification requirements. (The mission asked for `docs/17_...`;
  `17` was already taken by Search Memory — used the next free number.)
- `tests/connectors/sdk/certification.py` — a reusable `ConnectorCertificationMixin`
  any connector's test file can mix in to certify SDK compliance.
- 54 new tests (256 total): SDK unit tests, a template-method test suite (scripted
  fake connectors), certification tests for both reference connectors, and
  registry/factory performance tests with hundreds of registered connectors.

### Changed
- `demo_platform.py`/`demo_platform_two.py` rebuilt on `BaseConnector` — each now
  implements exactly `build_url`/`parse`/`normalize`/`connector_info` instead of one
  `search()` method that duplicated the same fetch->save->parse sequence.
- `core/agent.py`: connectors obtained only via `ConnectorFactory.get(platform)`; the
  old `_load_connector`/`Connector` ABC removed (nothing needed the `module.CONNECTOR`
  attribute convention once the Factory existed). Per-platform timing/success/failure
  now comes from each connector's own `ConnectorResult`, removing a second, redundant
  `time.perf_counter()` measurement in the orchestrator.
- `knowledge_service.connector_health()` gained an optional `platform_id` filter
  (backward-compatible, defaults to the old all-platforms behavior) so
  `BaseConnector.health_check()` can ask for just its own platform's health.
- `connectors/base.py` now holds only `RawListing` — completely unchanged in shape;
  every connector, regardless of source format, still produces this one shape.

### Not redefined (reused instead)
- `ConnectorHealth` is `src.knowledge.models.ConnectorHealth` (v2.0 Step 4), re-exported
  from the SDK, not a second competing class.

## [2.0.5] — 2026-07-15 — Architecture Cleanup

A small, explicitly-scoped cleanup pass following an architecture review (no blockers
found) — done between Version 2.0 Step 4 and Step 5. No behavior changes.

### Changed
- `storage/knowledge_repository.py` renamed to `storage/reference_data_repository.py`
  — it was colliding in name with the unrelated new `src/knowledge/` package.
  `analyzers/enricher.py`'s comment referencing the old name updated to match.

### Added
- Migration `0002_search_requests_created_at_index.sql` — adds
  `idx_search_requests_created_at`; `search_requests` had no index beyond its primary
  key despite being scanned and sorted by `created_at` on every completed search.
  `0001` untouched.
- 2 new migration tests (`Migration0002IndexTests`); two existing migration tests'
  applied-version assertions updated from `[1]` to `[1, 2]`.

### Documentation
- `docs/17_Search_Memory.md` — new "Two Reconstruction Helpers, Not One" section
  explaining why `history_service.previous_version()` and
  `search_memory_service._value_as_of()` both exist and aren't merged.
- `docs/01_System_Architecture.md` — new "Repository Writes vs. Service Layer" section
  formalizing the rule `analyzers/engine.py`'s direct `search_memory_repository` write
  already followed (and `apartment_history_repository.add_image_event` before it).
- `docs/03_Data_Model.md` — `ranking_usefulness_score`'s "exact formula TBD" note was
  stale (implemented in Step 4); updated to state the actual formula. Its Open
  Questions entry removed accordingly.

### Reviewed, no change needed
- No source-code `TODO`/`FIXME`/`XXX` comments existed anywhere in `src/`/`tests/`.
- No circular imports, oversized classes, or repository-consistency issues found.

200 tests passing (198 existing + 2 new).

## [2.0.4] — 2026-07-14 — Knowledge Engine

Fourth step of the Version 2.0 implementation (see `docs/10_Roadmap.md` "Implementation Order").

### Added
- `src/knowledge/` — the Knowledge Engine: `models.py` (`PlatformKnowledge`,
  `ConnectorHealth`, `CityKnowledge`, `KnowledgeSummary`), `metrics.py` (pure
  `extraction_quality_score`, `image_quality_score`, `availability_quality_score`,
  `duplicate_rate`, `ranking_usefulness_score`), `knowledge_service.py`
  (`record_platform_observation`, `best_platforms`, `platform_reliability`,
  `connector_health`, `average_city_price`, `knowledge_summary`,
  `platform_statistics`, `city_statistics`).
- `storage/platform_intelligence_repository.py` — `platform_performance_observations`
  data access.
- `discovery/platform_registry.py` gained `update_platform_rollups` (five of the six
  Platform Intelligence rollup columns; `connector_version` stays dormant).
- `RentalResearchAgent.run()` now captures per-platform metrics after every connector
  call (success or failure), then records one complete Knowledge Engine observation
  per platform per search — after ranking and after Search Memory's completion, per
  the mission's explicit Apartment History -> Search Memory -> Knowledge Engine
  ordering.
- "Cities"/"Connectors"/"Searches" knowledge (beyond the original docs/16 design) —
  all computed on demand from already-stored data, no new schema: `city_statistics`/
  `average_city_price` aggregate over `search_observed_apartments`/`apartments`;
  `connector_health` re-groups platform observations; search-level stats reuse Search
  Memory's existing `search_statistics()` rather than reimplementing it.
- 42 new tests (198 total): metrics unit tests, knowledge-service tests (including a
  recent-window-only rollup test and a 500-observation performance test), repository
  round-trip tests, and a new core-agent integration test file.

### Fixed
- `connectors/base.py`'s `RawListing.status` used to default to the literal string
  `"available"`, making "the connector explicitly said available" and "the connector
  said nothing" indistinguishable — exactly what `availability_quality_score` needs
  to detect. Changed the default to `None`; the actual "default to available"
  behavior already lived in `normalizer.py` (`raw.status or "available"`) and needed
  no change. Both reference connectors set `status` explicitly, so this is a
  zero-behavior-change fix.

### Not included (explicitly deferred or out of scope)
- No AI, predictions, or automatic decision-making anywhere in this engine — every
  value is a plain count, average, or ratio over already-stored facts.
- "Most common property types" (mentioned in the mission's CITIES tracking) is not
  implemented — no per-apartment property-type field exists anywhere in the schema
  (V1.0 scoped to residential apartments only); adding one would be new schema, out
  of this step's "only accumulate evidence" scope.
- No Connector SDK, Dynamic Filter Engine, or Deep Analysis Engine — still designed
  only (Steps 5–7).

## [2.0.3] — 2026-07-14 — Search Memory & Comparison Engine

Third step of the Version 2.0 implementation (see `docs/10_Roadmap.md` "Implementation Order").

### Added
- `src/search_memory/` — the Search Memory & Comparison Engine: `models.py`
  (`SearchExecution`, `SearchComparison`, `SearchStatistics`, `SearchTimeline`,
  `ApartmentPriceChange`, `ApartmentAvailabilityChange`, `PlatformCoverageChange`),
  `comparison.py` (pure `diff_apartment_sets`, `platform_coverage_change`,
  `search_quality`), `search_memory_service.py` (`record_completed_search`,
  `latest_search`, `search_history`, `search_timeline`, `compare_searches`,
  `average_execution_time`, `average_apartment_count`, `search_statistics`).
- `storage/search_memory_repository.py` — `search_observed_apartments` data access,
  `complete_search_execution` (the run-stats completion `UPDATE` on
  `search_requests`), `find_previous_search`, `get_search_history`.
- `storage/search_repository.py` gained a shared `row_to_search_request()` helper.
- `analyzers/engine.py` now writes a `search_observed_apartments` row for every
  processed listing.
- `RentalResearchAgent.run()` now times itself, tracks discovered vs. successfully
  searched platforms and each connector failure's exception message, and calls
  `record_completed_search()` automatically after report generation — every search
  now permanently remembers its own full execution, with no manual wiring.
- 34 new tests (156 total): comparison unit tests, service-level tests (including
  the run-over-run comparison scenario and repeated-search/append-only regression
  tests), repository round-trip tests, and a new core-agent integration test file.

### Fixed
- A real bug in the run-over-run "changed" comparison, found by running the actual
  CLI twice against the same unchanged data (not just unit tests): the original
  timestamp-window design counted a search's *own* initial-observation writes as
  changes relative to itself, since those writes happen strictly after that search's
  `created_at` (processing takes real time). Fixed by bounding the comparison by
  `search_id` identity first. See `docs/17_Search_Memory.md` "A Real Bug".
- A pre-existing doc typo: `docs/03_Data_Model.md` said "eight new columns" for the
  Search Memory `search_requests` extension; it's nine — corrected.

### Not included (explicitly deferred to later Version 2.0 steps)
- No Knowledge Engine logic (`platform_performance_observations`, Platform
  Intelligence rollups) — schema only, as before.
- No AI or predictive logic anywhere in this engine — every figure is a plain
  average or set/timestamp comparison over already-stored data.

## [2.0.2] — 2026-07-14 — Apartment History Engine

Second step of the Version 2.0 implementation (see `docs/10_Roadmap.md` "Implementation Order").

### Added
- `src/history/` — the Apartment History Engine: `models.py` (`Change`/`ChangeType`,
  the structured comparison result every method below produces), `comparison.py`
  (pure functions: `compare_price`, `compare_availability`, `compare_title`,
  `compare_description`, `compare_coordinates`, `compare_images`, `compare_presence`,
  `summarize_listing_updated`), `history_service.py` (`record_new_apartment`,
  `record_reobservation`, `latest_version`, `previous_version`, `price_timeline`,
  `availability_timeline`, `change_timeline`).
- `storage/apartment_history_repository.py` — data access for `apartment_change_log`
  and `apartment_image_events` (schema already existed since migration 0001; this adds
  the first real reads/writes).
- `storage/apartment_repository.py`: `update_apartment_details` (title/description),
  `mark_image_not_current`.
- `connectors/base.py`'s `RawListing` and `analyzers/normalizer.py` gained
  `description`.
- `analyzers/engine.py`'s write sequence now also writes `apartment_change_log` rows
  for title/description changes and runs Image Change Detection — one unified
  `_sync_images` function replacing the old `_collect_images`, used for both new and
  re-observed apartments (a new apartment has no prior images, so every URL is
  naturally "added," in original order — behavior-identical to before).
- 43 new tests (122 total): comparison unit tests, history-service tests (including a
  reconstructed-`previous_version` test and a 500-row change-timeline performance
  test), repository round-trip tests, engine-level regression/integration tests.

### Fixed
- Nothing was tracking title/description/image changes before this — a listing's
  title being edited, or a photo being added or removed, was invisible; only its
  current value was known, with no way to see it change over time. Now every such
  change is appended to `apartment_change_log`/`apartment_image_events`, never
  overwritten.

### Not included (explicitly deferred to later Version 2.0 steps)
- `compare_coordinates` and `compare_presence` ("listing removed"/"listing returned")
  are implemented and unit-tested but not wired into the pipeline: no connector
  populates coordinates yet (Step 7), and "removed" needs Search Memory's
  full-observed-set comparison (Step 3) to mean "gone from the platform" rather than
  "excluded by this run's filters."
- No Knowledge Engine logic, no Search Memory (`search_observed_apartments`, run-stats
  columns) — schema only, as before.

## [2.0.1] — 2026-07-14 — Migration Framework

First step of the Version 2.0 implementation (see `docs/10_Roadmap.md` "Implementation Order").

### Added
- `storage/migrations/` — numbered SQL migration files, applied automatically on startup.
- `schema_migrations` tracking table, so a migration never runs twice.
- `storage/migrations/0001_v2_knowledge_engine.sql` — the entire Version 2.0 schema
  designed on 2026-07-14: 6 new tables (`apartment_change_log`, `apartment_image_events`,
  `search_observed_apartments`, `platform_performance_observations`,
  `filter_definitions`, `apartment_analysis_metrics`) and new nullable columns on
  `platforms` (+6), `apartments` (+1), `apartment_images` (+2), `search_requests` (+9).
- New fields on the `Platform`, `Apartment`, `ApartmentImage`, and `SearchRequestRecord`
  dataclasses, and corresponding read/write updates in `discovery/platform_registry.py`,
  `storage/apartment_repository.py`, `storage/search_repository.py`.
- Migration framework tests: migrating a pre-migration database in place, idempotent
  repeated startup, failed-migration rollback, and version-ordered (not alphabetical)
  application.

### Fixed
- The database no longer needs to be deleted and regenerated for a schema change — the
  v1.1 `platforms` rework required a reset; this migration, and every additive one after
  it, does not. See `learning/database_notes.md`.
- A real transactional-DDL bug found while building the rollback test: Python's
  `sqlite3` module doesn't implicitly open a transaction before `CREATE`/`ALTER`
  statements the way it does for `INSERT`/`UPDATE`, so a failed migration's earlier
  `CREATE TABLE` was committing immediately regardless of a later `rollback()` call. Fixed
  by having the migration runner manage its own explicit `BEGIN`/`COMMIT`/`ROLLBACK`
  transaction rather than relying on the driver's implicit-transaction heuristic. See
  `learning/python_notes.md`.

### Not included (explicitly deferred to later Version 2.0 steps)
- No business logic for the 6 new tables — Apartment History, Search Memory, the
  Knowledge Engine, the Dynamic Filter Engine, and the Deep Analysis Engine are schema
  only in this step. Nothing writes to `platform_performance_observations`,
  `apartment_change_log`, etc. yet.

## [2.0] — 2026-07-14 — Autonomous Rental Intelligence Platform (design)

Architecture-only — no code changes. Full design across `docs/00`, `docs/03`–`docs/07`,
and three new docs (`docs/15_Agent_Architecture.md`, `docs/16_Knowledge_Engine.md`,
`docs/17_Search_Memory.md`). See `docs/10_Roadmap.md` "Version 2.0" for the complete
scope: Knowledge Engine, Apartment History, Search Memory, Platform Intelligence, Dynamic
Filter Engine, Deep Analysis Engine, Connector SDK, and the multi-agent naming convention.
An 8th core principle was added: learning happens through data, never by rewriting code.

## [1.1] — 2026-07-14 — Multi-Platform Discovery Framework

- Reworked the `platforms` table: `country`, `supported_cities`, `rental_types`,
  `homepage`, `search_url`, `requires_login`, `connector_available`, `connector_name`,
  `last_verified`, `discovery_method` replace `base_url`/`connector_module`/`is_active`.
- `DiscoveryAgent.sync_platforms()` — load existing platforms, detect duplicates (exact
  id or normalized homepage domain), update metadata, save new platforms, mark
  unsupported ones without deleting them.
- `discovery/known_platforms.py` — 2 reference connectors plus 6 real, well-known rental
  platforms across 4 countries, catalogued as `connector_available = False`.
- `ui/cli.py` syncs the known-platforms list on every startup.

## [1.0] — 2026-07-14 — Rental Intelligence Platform, V1.0

The full pipeline, end-to-end, proven against two reference connectors
(`demo_platform`, `demo_platform_two`) rather than a real commercial site, since no real
platform target had been chosen yet:

- Storage foundation: SQLite schema, repositories, versioned price/availability history.
- Platform Registry + Discovery Agent (static registry).
- Collectors (browser/HTTP fetch, image download, raw-page persistence).
- Connector contract, the Analysis Engine (normalize/dedupe/change-detect/enrich),
  and `RentalResearchAgent` — the real orchestrator.
- Ranking Engine (extensible criteria registry) and an HTML Report Generator.
- `ui/cli.py` — the real entry point.
- Re-run/compare proof: a second search after a real data change accumulates history
  instead of overwriting it.
- A second connector, with a deliberately different page structure, proving the
  platform-independence boundary holds without touching other modules.

## [0.1] — 2026-07-12 — Working prototype before platform architecture

Early prototype work predating the documented architecture — a config-driven search
concept (`config/settings.json`), a basic `Apartment`/`Configuration` model, and a
Playwright browser-launch stub. Confirmed stale and superseded once the V1.0 architecture
was designed; not migrated forward. See `learning/architecture_notes.md`.
