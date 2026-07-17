# MASTER_SPEC — Autonomous Rental Intelligence Platform

Version 2.5.0-rc1. This document is generated from the real implementation,
migrations, tests, CLI commands, API routes, and the numbered `docs/`
series — every claim below is traceable to real code or to a documented,
explicitly-deferred future scope. It is the single entry point for a new
developer; the numbered `docs/` files remain the authoritative detail behind
each section.

## 1. Mission and Product Scope

An autonomous platform that searches, ranks, monitors, and explains rental
apartment listings across multiple platforms, for residential apartments
(docs/00_Project_Vision.md). Every search is reproducible, every decision is
explainable, no business logic is ever tied to one specific website's
markup, and nothing is ever fabricated when evidence is missing.

## 2. Supported and Deferred Functionality

**Supported (implemented, tested)**: multi-platform discovery, a real
production connector (RentCast) plus deterministic demo/reference
connectors, apartment history, search memory, a knowledge engine, dynamic
filtering, geographic enrichment, explainable ranking (V1 + V2), user
feedback/preference learning, continuous monitoring, notification delivery
(console/file always-on, email/webhook once configured), a web dashboard +
JSON API, backup/restore, a local job runner.

**Deferred (explicitly out of scope, see each area's own doc)**: mobile
apps, multi-tenant billing, autonomous connector generation, a real task
queue (Celery/Redis), full multi-user authentication, an OS-level scheduler
inside the web server, PDF reports (HTML/JSON only), literal walking/transit
*time* filtering (today's filters are a normalized proximity score — see
docs/25 and docs/33's "Known Gaps").

## 3. Design Principles

From docs/00_Project_Vision.md, enforced throughout: (1) never discard data
that succeeded elsewhere just because one platform failed; (2) business
logic never depends on one website's specifics — only `connectors/` may;
(3) history is append-only, never overwritten; (4) every search is
reproducible from its stored criteria; (5) never fabricate a value for
missing evidence — label it honestly instead.

## 4. Complete Architecture

See docs/01_System_Architecture.md for the full pipeline diagram. Summary:
`RentalResearchAgent` (`core/agent.py`) orchestrates Discovery → Connectors
→ Analysis → (optional) Filter Engine → (optional) Geographic Engine →
Ranking (V1, optionally re-scored by Ranking V2) → (optional) Feedback →
Report Generation → Search Memory/Knowledge Engine recording. Every stage is
independently testable; the orchestrator only sequences and isolates
failures. `MonitoringEngine` and `NotificationEngine` sit above this,
reusing it unchanged; `src/web/` sits above all of it, reusing every engine
unchanged through one `WebServiceFacade`.

## 5. Agent Responsibilities

| Agent/Engine | Owns | Doc |
|---|---|---|
| `RentalResearchAgent` | End-to-end search orchestration | 01, 15 |
| `AutomaticDiscoveryAgent` | Platform candidate discovery | 29 |
| `MonitoringEngine` | Saved-search scheduling + change detection | 30 |
| `NotificationEngine` | Eligibility + delivery of monitoring events | 31 |
| `FeedbackEngine` | Preference learning from user actions | 28 |
| `FilterEngine` | Dynamic, composable hard-filtering | 25 |
| `GeographicEngine` | Distance/travel-time/nearby enrichment | 26 |
| `RankingEngineV2` | Explainable, evidence-based scoring | 27 |
| `WebServiceFacade` | The one call surface for every web route/API endpoint | 32 |

## 6. Package and Folder Guide

See docs/02_Folder_Guide.md for the complete, current tree. Top level:
`src/` (all source), `data/` (SQLite DB + media/raw-pages/cache, gitignored),
`output/` (generated reports, gitignored), `docs/` (this series), `tests/`
(mirrors `src/` 1:1, plus `tests/acceptance/` and `tests/scripts/`),
`scripts/` (backup/restore/health-check, added Step 17), `learning/` and
`notes/` (project journal and raw research).

## 7. Dependency Rules

Only `connectors/` may reference platform-specific structure (Principle 2,
enforced by code review convention, not a lint rule). A repository function
may be called directly by the module that owns the business decision to
write (e.g. `analyzers/engine.py` → `apartment_repository`); cross-cutting
orchestration (monitoring, notifications, web) calls a domain module's own
`service.py`, never a `*_repository.py` directly. See docs/01 "Repository
Writes vs. Service Layer".

## 8. Data Flow

`SearchRequest` → `DiscoveryAgent.discover()` → per-platform `Connector.search()`
→ `RawListing` → `analyzers/engine.py::process_listings()` (normalize, dedupe,
history) → `Apartment` rows → `AnalysisEngine` → (optional) `FilterEngine` →
(optional) `GeographicEngine` → `RankingEngine` (+ optional `RankingEngineV2`)
→ `search_results` → `generate_report()` → `search_memory_service`/
`knowledge_service` recording. Monitoring re-runs this same pipeline per
saved search on a schedule/manually, diffing against the previous run.
Notifications separately read `MonitoringEvent`s and decide delivery.

## 9. Database Tables

11 migrations, purely additive, never modifying a prior one — full detail
in docs/03_Data_Model.md. Groups: core (`platforms`, `apartments` + history
tables, `search_requests`/`search_results`), Search Memory
(`search_observed_apartments`), Knowledge Engine
(`platform_performance_observations`), Filter Engine
(`filter_definitions`, `filter_execution_history`), Geographic Engine
(`geo_enrichment_history`), Feedback (`feedback_events`,
`preference_observations`/`_adjustments`/`_snapshots`), Discovery
(`discovery_runs`, `platform_candidates`, evidence/verification/capability/
duplicate/provider-observation tables), Monitoring (`saved_searches`,
`saved_search_versions`, `monitoring_schedules`/`_runs`/`_events`,
`event_acknowledgements`, `monitoring_statistics`, `report_artifacts`),
Notifications (`notification_preferences`/`_versions`, `_templates`,
`_batches`, `_deliveries`, `_delivery_events`, `_digests`, `_attempts`,
`_messages`, `rate_limit_observations`, `channel_health_observations`,
`notification_acknowledgements`), Web (`web_jobs`, `web_ui_preferences`,
`web_saved_comparisons`, `web_recent_views`).

## 10. Migration System

`Database.__init__()` applies `schema.sql` then every `NNNN_*.sql` file
under `src/storage/migrations/` in ascending numeric order, each in its own
explicit `BEGIN`/`COMMIT`/`ROLLBACK` transaction (not Python's own implicit
transaction handling, which doesn't cover DDL — see `storage/database.py`'s
own docstring), recording applied versions in `schema_migrations`. Idempotent
— already-applied versions are skipped. Never modify a shipped migration;
add a new numbered file instead.

## 11. Search Request Model

`SearchRequest` (docs/04_Search_Request.md): `location` (free-text string —
see docs/33 "Known Gaps" for why a structured shape remains an open
question), `criteria` (a flat dict validated against the Dynamic Filter
Engine's registry at construction time), `id`/`created_at`/`label`.
Serialized verbatim to `search_requests.criteria_json` for reproducibility.

## 12. Dynamic Filter Engine

`src/filter_engine/` (docs/25): 39 self-registering filters (a handful
data-backed against real `Apartment` fields, most "dormant" — honestly
always-passing until a connector populates the field they'd check),
AND/OR/NOT/nested composition, `FilterStatistics`, `FilterHistory`. The web
dashboard's dynamic filter form is generated directly from
`FilterRegistry.all()` — no filter's logic is duplicated in `src/web/`.

## 13. Platform Discovery

Two systems: the original `discovery/` (a static, curated `Platform`
registry, docs/05) and `discovery/automatic/` (docs/29, v2.5 Step 13) — a
provider-independent agent that finds, deduplicates, classifies, verifies,
and estimates capabilities for candidate platforms, storing everything
append-only. Never auto-activates a platform for real searching; only an
explicit `approve-candidate` (CLI or web) does, and only when a certified
connector actually exists.

## 14. Connector SDK

`src/connectors/sdk/` (docs/18): `BaseConnector` (template method),
`ConnectorFactory`/`ConnectorRegistry`, structured validation/errors/
metadata. Every real connector (`demo_platform`, `demo_platform_two`,
`rentcast`, `sample_json_feed`) is built on this, the only sanctioned way to
obtain a connector instance.

## 15. Provider Framework

`src/providers/` (docs/21, docs/24): a common interface + factory +
configuration + scoring router (with fallback) + health/metrics/statistics/
validation, for both data providers (RentCast, local demo) and AI providers
(Ollama, a null/no-op fallback). Optional — every existing caller that
doesn't opt in is unaffected.

## 16. Apartment History

`src/history/` (docs/07, v2.0 Step 2): append-only `Change` records for
title/description generic fields; price/availability history and image
add/remove events live in their own dedicated tables, written directly by
`analyzers/engine.py`. Full timelines reconstructed on read, never stored as
a single "version" snapshot.

## 17. Search Memory

`src/search_memory/` (docs/17, v2.0 Step 3): records every completed
search's full execution stats (`SearchExecution`) and computes run-over-run
comparisons (`SearchComparison`, `diff_apartment_sets`) — what Continuous
Monitoring's own change detection builds directly on top of.

## 18. Knowledge Engine

`src/knowledge/` (docs/16, v2.0 Step 4): per-search platform performance
observations, recomputed Platform Intelligence rollups (reliability,
success rate, avg response time), a knowledge summary. Purely observational
— never an automatic decision-maker.

## 19. Geographic Intelligence

`src/geography/` (docs/26, v2.5 Step 10): a provider-independent engine —
distance/travel-time calculators, nearby search (17 categories), caching,
one real built-in provider (`haversine`). Never mutates the `Apartment` it
enriches; degrades honestly (empty result, never fabricated) when there's no
coordinate or no curated reference point.

## 20. Ranking Engine V2

`src/ranking_v2/` (docs/27, v2.5 Step 11): 12 self-registering, explainable
rules combining evidence from every engine above, user-configurable weights,
full per-apartment `RankingExplanation` + `RankingConfidence`. Never
hard-filters itself — that stays the Filter Engine's/`RankingEngine` v1's
job. Its own explanation has no persisted table; the web layer captures it
in-memory per job (see docs/32's own note on `SearchRunResult.ranking_v2_results`).

## 21. Feedback Engine

`src/feedback/` (docs/28, v2.5 Step 12): 23 self-registering preference
rules learning only from explicit, append-only user-action evidence,
deterministic decay/confidence math (no ML), three modes
(`EXPLICIT_ONLY`/`SUGGESTED`/`ASSISTED`), full undo/reset/explain/compare
auditability. Never infers a sensitive personal trait — verified by
`tests/acceptance/test_journey_e_feedback_ranking.py`'s own denylist scan.

## 22. Monitoring

`src/monitoring/` (docs/30, v2.5 Step 14): versioned saved searches (every
edit is a new immutable version), a database-backed due-time/claim
scheduling interface (any of cron/Task Scheduler/manual CLI/the web
dashboard's "Run now" can drive it), 5 self-registering event detectors,
deterministic significance/dedup/removal-threshold logic, full + change-only
HTML/JSON reports.

## 23. Notifications

`src/notifications/` (docs/31, v2.5 Step 15): reads `MonitoringEvent`s
read-only (never modifies one); versioned preferences; content-based
eligibility separate from time-dependent quiet-hours/rate-limiting; four
self-registering channels (console/file always-on, email/webhook once
configured); idempotent retry with exponential backoff; digest generation.

## 24. Web Dashboard

`src/web/` (docs/32, v2.5 Step 16): a local, single-user Flask app —
`WebServiceFacade` is the only thing every route calls; a thread-based
`JobRunner` for long-running work; server-rendered Jinja2 + minimal vanilla
JS. CSRF, security headers, path-traversal-safe id/file handling,
localhost-only default binding.

## 25. JSON API

`/api/v1/` (docs/32 "API Structure"): searches/search-jobs, apartments
(+history), saved searches, monitoring events, notifications, feedback, the
learned preference profile, discovery runs/candidates, platforms, health —
the same facade as the HTML routes, structured JSON errors.

## 26. CLI Commands

`src/ui/cli.py` (search), `monitoring_cli.py`, `notification_cli.py`,
`feedback_cli.py`, `discovery_cli.py` — every one thin, calling straight
into the same engines the web layer uses. Unchanged and fully supported
since before the web dashboard existed; see docs/33's backward-compatibility
tests.

## 27. Reports

HTML (and equivalent JSON) only, by explicit decision (docs/09,
notes/Questions.md "Answered") — structured data already lives durably in
SQLite regardless of report format. Generated per search run and per
monitoring run (full + change-only variants) and per discovery run.

## 28. Backup and Restore

`scripts/backup.py`/`restore.py`/`verify_backup.py` (v2.5 Step 17, docs/35):
timestamped, checksummed, optionally-compressed backups of the database
(via SQLite's own online backup API), raw pages, media, reports, and
non-secret configuration — never `.env`/`.web_secret_key`/channel
credentials. Restore requires an explicit destination and refuses to
overwrite a non-empty one without `--force`; a restored database is
integrity-checked automatically.

## 29. Security Model

See docs/34_Security_Acceptance.md for the full matrix. Summary: CSRF on
every state-changing HTML request, Jinja2 autoescaping (XSS), parameterized
SQL everywhere (no string-built queries), path-traversal-safe id/file
handling, `http`/`https`-only URL validation, secret redaction in every
channel-status surface, localhost-only default binding, no raw tracebacks,
request-size limits.

## 30. Privacy Boundaries

Feedback/preference learning never infers a sensitive personal trait (race,
religion, ethnicity, nationality, health, disability, sexual orientation,
immigration status) — enforced by a hard denylist scan in acceptance
testing, since every registered preference key is a real, named,
inspectable Python identifier, not a black-box output. Notification channel
configuration is never rendered with its secret fields. No sensitive search
criteria are logged beyond what's already persisted in `search_requests`
(itself local-only, never transmitted anywhere).

## 31. Configuration

`.env` (never committed) plus `src/core/config.py` (paths) and
`src/web/configuration.py` (web host/port/binding/secret-key). Every
variable: `.env.example`. Full reference: docs/35 "Configuration Reference".

## 32. Testing Strategy

Real, deterministic tests throughout — demo connectors serve local
Playwright-rendered fixtures (never live commercial sites in automated
tests); fake `PageFetcher`/mock HTTP/fake SMTP transports for discovery and
notifications; `tests/acceptance/` drives real user journeys end-to-end
through the actual Flask app object. 1291+ tests, 0 skipped, 0 failures as
of this release candidate (see docs/33 Phase 1/Phase 11).

## 33. Development Workflow

Strict sequence per sprint (see `learning/architecture_notes.md`'s own
running journal): answer preliminary questions → implement → write tests →
update every relevant doc → run the full suite → demonstrate real
functionality live → commit with an exact `"Version 2.5 Step N - <Name>"`
message. Backward compatibility preserved via optional/default-`None`
parameters at every integration point.

## 34. Adding a Connector

See docs/18_Connector_SDK.md — subclass `BaseConnector`, implement
`build_url`/`parse`/`normalize`/`connector_info`, decorate with
`@register_connector`. No other file needs to change.

## 35. Adding a Provider

See docs/21/docs/24 — subclass `DataProvider`/`AIProvider`, register via
`register_provider()`. `ProviderRouter` picks it up automatically.

## 36. Adding a Filter

See docs/25 — subclass `BaseFilter`, implement `validate`/`apply`/`metadata`,
call `register_filter()` at module import time. The web dashboard's dynamic
form picks it up automatically — no web-layer change needed.

## 37. Adding an Analyzer

See docs/19_Analysis_Engine.md — subclass `BaseAnalyzer`, register via
`register_analyzer()`. `AnalysisEngine`/`AnalysisPipeline` run it
automatically for every apartment.

## 38. Adding a Ranking Rule

See docs/27 — subclass `RankingRule`, register via `register_ranking_rule()`.
Contributes to every `RankingProfile`'s renormalized weighted score
automatically.

## 39. Adding a Feedback Rule

See docs/28 — subclass `PreferenceRule` (or one of its 4 shared aggregate
bases), register via `register_preference_rule()`. Must never target a
sensitive personal trait (see "Privacy Boundaries" above).

## 40. Adding a Monitoring Event (Detector)

See docs/30 — subclass `EventDetector`, register via
`register_event_detector()`. Runs as part of every monitoring execution's
step 6-9 detection pass.

## 41. Adding a Notification Channel

See docs/31 — subclass `NotificationChannel`, implement `configure`/
`validate_configuration`/`send`/`channel_info` (never echo a secret from
`channel_info()`), register via `channels/__init__.py`'s eager import.

## 42. Adding a Web Route

See docs/32 "How to Add a New Page"/"How to Add a New API Endpoint" — add a
facade method if needed, a route function in the relevant blueprint, a
template extending `base.html`, and (for API) serialize with
`to_jsonable()`. Never SQL, never a recomputed business decision, in the
route itself.

## 43. Deployment Assumptions

Single local user, single process, SQLite as the only datastore, localhost
binding by default. No containerization, no orchestration, no external
message broker assumed — `JobRunner`'s thread-based design and the
migration system's file-based versioning are both deliberately simple
enough to require none of that for this release.

## 44. Known Limitations

See docs/33_Release_Candidate_Acceptance.md "Known Gaps Found During
Acceptance" for the full, current list — most notably: `walking_distance`/
`public_transport_time` filters are a proximity score, not literal minutes;
filter-value validation errors surface as a job's `error_summary` rather
than an immediate form-level 400; `property_type` cannot be meaningfully
exercised against demo connectors; `new_match`/`new_listing` monitoring
events require a genuine second observation to fire.

## 45. Open Decisions

See `notes/Questions.md` for the live, current list — as of this release:
which real task queue to adopt when scaling beyond one process, what the
real multi-user authentication mechanism should be, whether the comparison
page should eventually compute "true monthly cost"/"user-preference match",
which additional notification channel to build next, and several others
each tagged with which doc they block.

## 46. Version Roadmap

See docs/10_Roadmap.md for the complete, step-by-step history from V1.0
through Version 2.5 Step 17 (this release candidate). No Version 3.0 work
begins until this release candidate is accepted.

## 47. Glossary

See docs/12_Glossary.md for the full list. Load-bearing terms used
throughout this document: **Saved Search** (a versioned, monitorable search
definition), **Monitoring Event** (one detected change, append-only),
**Notification Delivery** (one logical notification, possibly multi-channel,
possibly retried), **Preference Profile** (a profile's current computed
preferences, explicit + inferred), **Discovery Candidate** (a platform found
by automatic discovery, not yet necessarily approved/connectable).

## 48. New-Developer Onboarding Checklist

1. `python -m venv .venv && .venv/Scripts/pip install -r requirements.txt`
   (or `.venv/bin/pip install -r requirements.txt` on macOS/Linux).
2. `python -m playwright install chromium`.
3. `cp .env.example .env`.
4. `python scripts/health_check.py` — every check should report `PASS` or a
   clearly-explained `WARN` (e.g. an unconfigured optional notification
   channel).
5. `python -m unittest discover -s tests -t .` — should report 0 failures.
6. `python -m src.ui.cli --location "Example City"` — confirms the CLI path
   works end-to-end.
7. `python -m flask --app "src.web.application:create_app" run`, open
   `http://127.0.0.1:5000/` — confirms the web path works end-to-end.
8. Read docs/01_System_Architecture.md, then docs/02_Folder_Guide.md, then
   whichever numbered doc covers the area you're about to touch.
9. Follow the Development Workflow (Section 33) for any change you make.

## Related Documents

Every numbered file under `docs/` (00 through 36), plus `README.md`,
`CHANGELOG.md`, `notes/Questions.md`, and `learning/architecture_notes.md`.
