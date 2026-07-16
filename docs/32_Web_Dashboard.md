# 32 — Web Dashboard & API

Version 2.5 Step 16. A real, server-rendered local web application on top of
everything built through Step 15 — Rental Research Agent, Automatic Platform
Discovery, Connector SDK, Production Providers, Apartment History, Search
Memory, Knowledge Engine, Dynamic Filter Engine, Geographic Intelligence,
Ranking Engine V2, Feedback/Preference Learning, Continuous Monitoring, and
Notification Delivery. It is **not** a rewrite or a replacement of any of
those — see "Architecture" below.

## Architecture

`src/web/` never contains business logic. Every HTML route and every JSON
API endpoint calls exactly one thing for data: `WebServiceFacade`
(`src/web/facade.py`), which in turn calls the exact same engines/services
every prior step already published (`RentalResearchAgent`, `MonitoringEngine`,
`NotificationEngine`, `FeedbackEngine`, `AutomaticDiscoveryAgent`,
`FilterRegistry`, `GeographicEngine`, storage repositories' own read
functions). This mirrors `MonitoringEngine`'s and `NotificationEngine`'s own
documented shape one layer up: "every heavy engine is reused exactly as
published — this module only adds orchestration on top."

```
Browser (HTML) ──┐                          ┌── JSON client (curl, a future mobile app, ...)
                  ▼                          ▼
           routes/*.py                  api/*.py
                  │                          │
                  └────────────┬─────────────┘
                                ▼
                      WebServiceFacade (facade.py)
                                │
        ┌───────────┬───────────┼───────────┬────────────┬─────────────┐
        ▼           ▼           ▼           ▼            ▼             ▼
RentalResearchAgent  MonitoringEngine  NotificationEngine  FeedbackEngine  AutomaticDiscoveryAgent  storage/* read fns
        │
        ▼
   JobRunner (jobs/runner.py) — background thread, persisted Job row (web_jobs)
```

### Why the web UI must remain separate from business logic

Every prior sprint built its own engine specifically so *any* interface could
drive it — the CLI, and now the web layer. If a route computed a ranking
score, applied a filter, or evaluated monitoring significance directly, the
web app would become a second, divergent implementation of rules that already
exist and are already tested. Routes never contain SQL or a business
calculation; they parse a request, call the facade, and render.

### Why existing services are reused instead of rewritten

`RentalResearchAgent`, `MonitoringEngine`, `NotificationEngine`,
`FeedbackEngine`, `AutomaticDiscoveryAgent` are already tested (1186 tests
before this step) and CLI-proven. Calling them is strictly less work and
strictly more correct than reimplementing any part of their behavior in a
route or template.

### Single-user today, multi-user tomorrow

`src/web/constants.py::DEFAULT_PROFILE_ID` is a fixed constant every facade
call threads through — the same `profile_id` parameter `feedback`/
`notifications`/`monitoring` already require. The only future change to
support multiple users is *where that value comes from* (a session/auth
lookup instead of a constant); no facade method signature, route, or template
would need to change.

### Why long-running searches need job-status handling

A real search run (discovery → connectors → analysis → ranking → report) can
take seconds to minutes. One HTTP request must not block that long, and a
browser refresh or server restart mid-run must not lose track of what
happened. See "Job Model" below.

### Why HTML and JSON share one service layer

Both are different renderings of the same facade calls. Keeping business
orchestration in the facade — never in a Jinja template, never duplicated
between a route and an API endpoint — means adding a JSON endpoint for
existing data, or an HTML page for an existing endpoint, can never drift out
of sync with the other.

## Framework Decision

**Flask**, chosen by inspecting the actual codebase rather than a default
preference:

- Every existing module is fully synchronous — `sqlite3`, `Database.transaction()`
  (a blocking context manager), every engine's own blocking calls. FastAPI's
  natural idiom is async routes over pydantic models; adopting it would mean
  either fighting the existing synchronous data layer or writing async routes
  that immediately block on sync I/O anyway.
- `grep -r "^import pydantic\|^from pydantic" src/` returns nothing — every
  model in this codebase is a plain dataclass (`storage/models.py`,
  `monitoring/models.py`, `notifications/models.py`, ...). `pydantic` in
  `requirements.txt` is only a transitive dependency of `openai`. FastAPI
  would introduce a second, competing modeling convention.
- Every existing UI layer (`ui/cli.py`, `monitoring_cli.py`, `notification_cli.py`,
  `feedback_cli.py`, `discovery_cli.py`) is a synchronous `argparse` CLI —
  Flask's synchronous request model matches that precedent directly.
- Flask bundles Jinja2, satisfying "prefer server-rendered HTML with
  progressive enhancement" with no extra templating dependency decision.

No heavy frontend framework is used — templates are Jinja2, styling is one
hand-written CSS file (`static/css/style.css`, CSS Grid + a handful of custom
properties, no build step), and the only JavaScript
(`static/js/app.js`, under 60 lines) does exactly two things: poll a job's
status via `fetch()`, and confirm before a destructive POST. Every page works
with JavaScript disabled except live job-progress polling (the page still
shows the job's status as of the last full load, and refreshing manually
still works).

## Startup Instructions

```bash
# from the project root, with .venv activated
python -m flask --app "src.web.application:create_app" run
# or, for local development with auto-reload:
python -m flask --app "src.web.application:create_app" --debug run
```

`create_app()` takes no required arguments — it builds a real
`WebConfiguration.from_env()` and a real `Database()` pointed at
`data/rental_intelligence.db` (same database the CLI and every engine already
use). Environment variables (see "Configuration" below) control host/port/
debug/network exposure. There is no separate `wsgi.py` — `create_app` *is*
the WSGI entry point a production server (gunicorn/waitress) would import the
same way.

## Route Structure

`src/web/routes/` — one Blueprint module per area, registered by
`routes/__init__.py::register_routes()`:

| Blueprint | URL prefix | Covers |
|---|---|---|
| `dashboard` | `/` | Main dashboard |
| `search` | `/search` | New search form, job status, results |
| `apartments` | `/apartments` | Apartment detail page |
| `comparison` | `/compare` | Save/view a 2-5 apartment comparison |
| `saved_searches` | `/saved-searches` | Create/view/version/run/compare saved searches |
| `monitoring` | `/monitoring` | Saved-search monitoring dashboard, event acknowledgement |
| `notifications` | `/notifications` | Preferences, channel status, deliveries, digests |
| `discovery` | `/discovery` | Manual discovery run, candidate review, approve/reject |
| `feedback` | `/preferences` | Feedback recording, preference profile, explain/undo/reset |
| `health` | `/health` | System health |

Every route function: parses `request.form`/`request.args` via `web/forms/`,
calls one or more `WebServiceFacade` methods, and either `render_template()`s
an HTML page or (when `Accept: application/json` is set) returns the same
data as JSON — see e.g. `routes/search.py::job_status()` and
`routes/apartments.py::detail()`.

## API Structure

`src/web/api/` — versioned under `/api/v1/`, one Blueprint module per entity,
registered by `api/__init__.py::register_api()`. Every endpoint calls the
same `WebServiceFacade` the HTML routes use and serializes with
`presenters/serialization.py::to_jsonable()` (a small recursive
dataclass/enum/datetime → plain-JSON converter, used everywhere so no
endpoint reinvents serialization slightly differently).

| Path | Entity |
|---|---|
| `/api/v1/search-jobs`, `/api/v1/searches/<id>` | Searches, search jobs |
| `/api/v1/apartments/<id>`, `/api/v1/apartments/<id>/history` | Apartments, apartment history |
| `/api/v1/saved-searches`, `/api/v1/saved-searches/<id>` | Saved searches |
| `/api/v1/monitoring-events` | Monitoring runs/events |
| `/api/v1/notifications/preferences`, `/deliveries`, `/channels` | Notifications |
| `/api/v1/feedback`, `/api/v1/feedback/history` | Feedback |
| `/api/v1/preferences` | The learned preference profile (distinct from notification preferences) |
| `/api/v1/discovery-runs`, `/api/v1/discovery-runs/candidates` | Discovery runs |
| `/api/v1/platforms` | Platforms |
| `/api/v1/health` | Health + statistics |

A validation error returns `{"error": "validation_error", "message": "..."}`
with HTTP 400; an unknown id returns `{"error": "not_found", ...}` with 404;
an unexpected server error returns `{"error": "internal_error", ...}` with
500 and never a raw traceback (`WebErrorHandler`, shared with the HTML
routes). The API is CSRF-exempt (see "Security Model") but still bound to
localhost by default like everything else.

### How to add a new API endpoint

1. Add a method to `WebServiceFacade` if the data isn't already exposed
   (most read endpoints reuse an existing method the HTML route also calls).
2. Add a route function in the relevant `api/*.py` module (or a new module,
   registered in `api/__init__.py`).
3. Serialize the return value with `to_jsonable()`.
4. If the endpoint accepts input, validate it with a `web/forms/` parser (or
   a small inline check raising `WebValidationError`) before calling the
   facade — never trust `request.args`/`request.form` directly.

## Service Facade

`WebServiceFacade` (`src/web/facade.py`) is grouped into the same sections as
this document: dashboard, search, apartments, comparison, saved searches/
monitoring, notifications, discovery, feedback, health/statistics. Every
method either delegates straight to an existing engine method, or does pure
read-aggregation (joining a `SearchResultEntry` with its `Apartment`, e.g.)
— never a scoring/filtering/eligibility decision.

`WebDependencies` (`src/web/dependencies.py`) constructs the engine instances
`WebServiceFacade` needs, once per process: `MonitoringEngine`,
`NotificationEngine`, `FeedbackEngine`, `AutomaticDiscoveryAgent`, and the
`JobRunner`. `RentalResearchAgent` is *not* a shared instance — it's built
fresh per search (inside `JobRunner._run_search()`), because its optional
`filter_engine`/`geo_engine`/`ranking_engine_v2` construction parameters vary
per request, exactly like every CLI invocation already builds its own.

### One real, additive change to `core/agent.py`

`RankingEngineV2`'s per-apartment explanation (score, confidence, top
factors) had no persisted form anywhere before this step — only v1's
`RankingEngine` output reaches `search_results`. To let the results/detail
pages show a real, non-fabricated ranking explanation without re-running
`RankingEngineV2` a second time (which would duplicate — not reuse — its own
logic), `core/agent.py::SearchRunResult` gained one new, optional field:

```python
@dataclass
class SearchRunResult:
    search_id: str
    apartments: list[Apartment]
    report_path: Path
    ranking_v2_results: list[RankedApartmentV2] | None = None  # new, defaults to None
```

`run()` already computed this value internally and previously discarded it;
it now hands it back. Every existing caller that doesn't pass
`ranking_engine_v2` (every CLI invocation, every existing test) sees
byte-identical behavior — confirmed by
`tests/web/test_backward_compatibility.py`. `JobRunner` captures this value
into the job's own `metadata_json["ranking_v2"]` (a per-apartment-id dict of
score/confidence/top factors) — job metadata, not a duplicate of any
existing table, and honestly scoped to "what this specific search run
computed," not a permanent apartment attribute.

## Job Model

See docs' own "Job Model" section in the mission and `src/web/jobs/`. A
`Job` (`jobs/models.py`) is the domain object; `WebJobRecord`
(`storage/models.py`) is its persisted row (migration `0011_web_dashboard.sql`,
table `web_jobs`) — the same domain/storage-dataclass separation
`NotificationDelivery`/`NotificationDeliveryRecord` already established.

Statuses: `pending` → `running` → one of `completed` / `partial` / `failed` /
`cancelled`. Stored fields: `job_id`, `job_type` (`search` /
`monitoring_run` / `discovery_run`), `profile_id`, `request_reference`,
`created_at`/`started_at`/`completed_at`, `status`, `progress` (a float
`0.0`-`1.0`), `current_stage`, `result_reference` (a search_id /
monitoring_run_id / discovery run_id — a foreign identifier into an existing
table, never a copy of its data), `error_summary`, `warnings`,
`cancellation_requested`, `metadata`.

### `JobRunner` — the local execution abstraction

`src/web/jobs/runner.py::JobRunner` runs one job per background
`threading.Thread`, against the same SQLite file every other caller uses
(`Database.transaction()` opens its own connection per call — the same
pattern already established everywhere in this codebase). No Redis/Celery:
correct and sufficient for one local user, one process.

Progress granularity is deliberately coarse: `pending` (0%) → `running`
(`current_stage="running_research_agent"`, no fabricated intermediate
percentage) → a terminal status at 100%. `RentalResearchAgent.run()` doesn't
expose a progress callback, and inventing fake intermediate percentages
would violate this project's own "never fabricate" discipline — the honest
choice is a real two-state progress bar, not a smooth-looking fake one.

Status determination reuses existing signals rather than guessing: a search
job's `completed`/`partial`/`failed` classification reads
`search_memory_service.get_search_execution()`'s own `searched_platform_ids`/
`failed_platform_ids` (exactly what `monitoring/engine.py`'s own
`_determine_status()` already reads); a monitoring-run job's status is a
direct copy of `MonitoringRunStatus` (the two enums share the same three
values by construction); a discovery-run job is always `completed` (the
Automatic Platform Discovery Agent's own design has no "failed" outcome —
provider failures are recorded as warnings on the run itself, not a run
failure).

### Future task-queue migration

Swapping `JobRunner`'s `threading.Thread` for a real task queue (Celery,
RQ, or a hosted equivalent) would only change the *inside* of
`start_search_job()`/`start_monitoring_run_job()`/`start_discovery_run_job()`
— enqueue a message instead of spawning a thread, and have a separate worker
process call the same `_run_search`/`_run_monitoring`/`_run_discovery`
functions. No route, form, template, or API endpoint would change, since
they only ever read a `Job` back via `jobs.service.get_job()` — the seam is
already isolated to one file.

## Form Lifecycle

`src/web/forms/` turns raw `request.form`/`request.args` into validated
keyword arguments for the facade — never a `SearchRequest`/ranking/filter
decision. `forms/validation.py` holds shared primitives
(`parse_safe_id` — rejects path traversal and disallowed characters;
`parse_optional_float`/`parse_optional_int` — reject non-numeric/negative/
out-of-range values; `parse_result_limit` — caps at 200; `parse_safe_url` —
`http`/`https` only). Every `WebValidationError` raised here becomes a
consistent 400 (HTML: the flashed-message-and-redirect pattern; JSON: a
structured `{"error": "validation_error", ...}` body) via `WebErrorHandler`.

The dynamic filter section of the search/saved-search forms is generated
directly from `FilterRegistry.all()` (`src/filter_engine/registry.py`) —
grouped by each filter's own `category` (`price`, `property`, `location`,
`amenities`, `platform`, `media`) and rendered by `value_type`
(`boolean`/`number`/`string`). This is the mission's explicit instruction —
"use the existing Dynamic Filter Engine, do not create duplicate filter
logic in the web layer" — applied literally: no filter's validation rule is
hand-copied into a form module; the 39 registered filters (12 data-backed,
26 dormant, one composite) drive the form automatically, and a future 40th
filter needs no web-layer change at all.

## Search Workflow

1. `GET /search/new` — `routes/search.py::new_search()` renders the
   multi-section form (location, the dynamic filter categories, output
   options) from `facade.available_filters()` and `facade.list_platforms()`.
2. `POST /search/new` — `forms/search_form.py::parse_search_form()` validates
   input; `facade.start_search()` builds a `Job`, persists it (`pending`),
   and hands off to `JobRunner` on a background thread; the response is an
   immediate redirect to `/search/jobs/<job_id>` — the request never blocks
   on the actual search.
3. `GET /search/jobs/<job_id>` — renders a page that polls itself (via
   `static/js/app.js::pollJob()`) against the same URL with
   `Accept: application/json`, until the job reaches a terminal status, then
   redirects to the results page.
4. `GET /search/results/<search_id>` — reads `search_results`/`apartments`/
   `apartment_analysis_metrics` (already persisted, real rows) plus the
   job's captured `ranking_v2` snapshot, and renders ranked apartment cards.

A platform whose connector fails mid-run doesn't abort the search (this was
already `RentalResearchAgent.run()`'s own behavior — see docs/01) — the job
still reaches `partial` (not `failed`) whenever at least one platform
succeeded or apartments were found, with the failed platform(s) named in
`job.warnings`.

## Saved-Search Workflow

`routes/saved_searches.py`: create (`POST /saved-searches/new`, delegating
straight to `MonitoringEngine.create_saved_search()`), view (immutable
versions listed via `monitoring_service.get_saved_search_versions()`),
create-a-new-version (`facade.update_saved_search()` →
`MonitoringEngine.update_saved_search()` — never overwrites, always appends),
enable/disable monitoring, run now (`facade.run_saved_search_now()` → a
`monitoring_run` job, same job-status page the search workflow uses), compare
runs (`monitoring_statistics.compare_monitoring_runs()`).

## Monitoring Workflow

`routes/monitoring.py::index()` lists every saved search with its enabled/
disabled state and every unacknowledged `MonitoringEvent`
(`monitoring_service.get_unacknowledged_events()`). Acknowledging an event
(`POST /monitoring/events/<id>/acknowledge`) calls
`MonitoringEngine`'s own acknowledgement path — never a direct
`monitoring_events` write from the web layer. No OS-level scheduler runs
inside the web server — "Run now" is the only trigger this UI offers,
exactly matching the mission's own "Do not implement an operating-system
scheduler inside the web server."

## Notification Workflow

`routes/notifications.py`: create a preference
(`forms/notification_form.py` validates channel names against
`NotificationChannelRegistry`, severity/digest-frequency/quiet-hours values),
view channel configuration status (`facade.channel_config_status()` →
`NotificationChannelMetadata.channel_info()`, which **never** includes a
password/signing secret — see "Security Model"), preview a rendered message,
list pending/delivered/failed deliveries, acknowledge/retry/cancel a
delivery, trigger "deliver pending notifications now"
(`NotificationEngine.process_pending_deliveries()`), and generate a manual
digest.

## Discovery Workflow

`routes/discovery.py`: a manual discovery run form (country/region/city/
rental categories) starts a `discovery_run` job
(`AutomaticDiscoveryAgent.run()`, unchanged); candidates are listed with
status/confidence/classification; a candidate's evidence/verification/
capability-estimate rows are shown on its detail page; approve
(`facade.approve_candidate()`, reusing the exact `DiscoveryAgent.sync_platforms()`
call `discovery_cli.py`'s own `approve-candidate` command makes) and reject
(marks `PlatformStatus.UNSUPPORTED`, records a `manual_review_decision`
evidence row — the same two operations the CLI already performs, called
through the facade instead of `argparse`). The web layer never triggers
scraping of a candidate directly — discovery only ever fetches a homepage to
verify accessibility/relevance, exactly as it always has.

## Feedback Workflow

`routes/feedback.py` (`/preferences`): record an action (`viewed`/`saved`/
`shortlisted`/`rejected`/`contacted`/`manual_rating`/`ranking_up`/
`ranking_down`/`original_listing_opened` — validated against
`feedback.event_types.KNOWN_EVENT_TYPES`), view the current preference
profile (`FeedbackEngine.build_preference_profile()`, mode selectable via
`?mode=explicit_only|suggested|assisted`), explain one preference's evidence
and adjustment history, undo a specific adjustment, reset every inferred
(never explicit) preference.

## Security Model

- **CSRF.** A per-session random token (`WebSecurity.csrf_token()`,
  `secrets.token_urlsafe(32)`, stored server-side in the signed session
  cookie) is rendered into every HTML form via `templates/_macros.html::csrf_field()`
  and compared (`secrets.compare_digest`, constant-time) on every non-GET/HEAD/
  OPTIONS request in `WebApplication`'s `before_request` hook — no route
  remembers to call this itself. `/api/` routes are exempt (not a browser-form
  target; still localhost-only by default).
- **Security headers.** `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, a restrictive
  `Content-Security-Policy`, and `Permissions-Policy` disabling geolocation/
  camera/microphone — applied to every response in `after_request`.
- **Path traversal.** `WebSecurity.safe_join()` reuses the exact defense
  `notifications/channels/file_channel.py::_resolve_path()` already
  established (resolve, then check the result is inside the base directory);
  `forms/validation.py::parse_safe_id()` additionally rejects any id
  containing `/`, `\`, `..`, or characters outside `[A-Za-z0-9_.-]` before it
  ever reaches a repository lookup.
- **URL validation.** `WebSecurity.is_safe_url()` accepts only `http`/`https`
  with a real host — rejects `javascript:`/`file:`/`data:`/schemeless
  strings anywhere a URL is user-supplied (e.g. a manual discovery URL).
- **Request-size limits.** `MAX_CONTENT_LENGTH` (default 5 MiB) rejects an
  oversized request body with a real 413, before Flask even parses the form.
- **Secret redaction.** Channel configuration is only ever exposed through
  `channel_info()` (built in Step 15 to never echo `password`/`signing_secret`)
  — the web layer never reads a channel's raw configuration object directly.
- **No raw tracebacks.** `WebErrorHandler` logs the real exception
  server-side and renders/returns a generic message — verified by
  `tests/web/test_security.py`.
- **Authentication extension points, not a full identity system.** Every
  facade call already takes a `profile_id`; there is no login page or
  session-identity concept yet (single local user, per the mission's own
  scope for this version) — see "Future Authentication Migration."

## Localhost Binding

`WebConfiguration.host` defaults to `127.0.0.1`. Setting the environment
variable `WEB_ALLOW_NETWORK=1` is the *one* explicit opt-in that changes the
default bind host to `0.0.0.0` (network-exposed) — nothing else in
`WebConfiguration`/`WebApplication` widens it implicitly, satisfying "require
explicit configuration to expose the application on the network."

## Configuration

Environment variables (all optional):

| Variable | Default | Effect |
|---|---|---|
| `WEB_HOST` | `127.0.0.1` (or `0.0.0.0` if `WEB_ALLOW_NETWORK=1`) | Bind host |
| `WEB_PORT` | `5000` | Bind port |
| `WEB_DEBUG` | off | Flask debug mode (auto-reload, interactive debugger — **never** enable outside local development) |
| `WEB_ALLOW_NETWORK` | off | The one opt-in to bind beyond localhost |
| `WEB_SECRET_KEY` | auto-generated, persisted to `data/.web_secret_key` (gitignored) | Session/CSRF signing key |

## Troubleshooting

- **"CSRF token missing or incorrect" on every form submit** — the browser
  session cookie was lost or the server restarted with a different secret
  key mid-session; reload the form page (a fresh token is issued) and
  resubmit.
- **A search job stays `running` far longer than expected** — check
  `job.current_stage`; the underlying `RentalResearchAgent.run()` call is
  synchronous inside the background thread, so a slow/hanging connector
  blocks that one job's thread, not the rest of the app (each job is its own
  thread).
- **`/health` shows a connector/channel as unhealthy** — this reads the exact
  same `knowledge_service.connector_health()`/`notification_service.compute_channel_health()`
  the CLI's own `monitoring-cli health`/`notification-cli channel-health`
  commands already expose; troubleshoot the underlying connector/channel the
  same way you would from the CLI.
- **A page shows "not available" everywhere** — this is the honest,
  intended behavior for data no connector/engine has ever populated for that
  apartment — not a bug. See "Never hide missing data by inventing values"
  in the mission text.

## How to Add a New Page

1. Add or extend a facade method for the data the page needs (reusing an
   existing engine call wherever possible).
2. Add a route function in the relevant `routes/*.py` blueprint (or a new
   blueprint, registered in `routes/__init__.py`).
3. Add a template under `templates/`, extending `base.html`, importing
   `_macros.html`'s `csrf_field()`/`data_value()`/`badge()` as needed.
4. If the page needs a form, add a parser in `web/forms/`.
5. Add it to `base.html`'s nav if it's a top-level section.

## Future Task-Queue Migration

See "Job Model" above — the seam is `JobRunner`'s three `start_*_job()`
methods; nothing else needs to change.

## Future Authentication Migration

Every facade method already threads a `profile_id`
(`DEFAULT_PROFILE_ID` today). Adding real multi-user auth means: a login
page/route, a session-stored user id, and changing exactly one place —
wherever `DEFAULT_PROFILE_ID` is currently passed to a facade call — to read
that session's user id instead. `WebSecurity`/`WebErrorHandler`/CSRF/session
cookie configuration are already real infrastructure this would build on top
of, not replace.

## Known Limitations (Honestly Documented, Not Hidden)

- The comparison page's "true monthly cost" (utilities/fees-inclusive) and
  "user-preference match" columns from the mission's own wishlist are **not**
  shown — no engine in this codebase computes either value yet; inventing a
  number for either would violate "never fabricate." The comparison page
  shows every genuinely computed/persisted field instead.
- `room_type` is always labeled "not available" — `Apartment` (storage/models.py)
  has no such field yet.
- Report format remains HTML-only (see `notes/Questions.md`'s already-answered
  "What output format does a report need?") — the web dashboard doesn't add a
  second format.
- `/api/v1/search-jobs` (job creation) accepts `application/x-www-form-urlencoded`
  bodies only, matching what the HTML form itself posts (multi-value fields
  like `enabled_platforms`/`filter__*` need `MultiDict.getlist()`, which a
  plain JSON body can't represent the same way) — every read endpoint
  (`GET`) returns JSON as usual.

## What's Deliberately Not Built

- No mobile application.
- No multi-tenant billing.
- No autonomous connector generation.
- No replacement of the existing CLI — `src/ui/cli.py` and every other
  `*_cli.py` are untouched and still the only way to drive this platform
  without a browser.
- No real task queue (Celery/RQ) — see "Future Task-Queue Migration."
- No full identity/authentication system — see "Future Authentication
  Migration."
- No OS-level scheduler inside the web server.

## Related Documents

- [01_System_Architecture.md](01_System_Architecture.md)
- [25_Dynamic_Filter_Engine.md](25_Dynamic_Filter_Engine.md) — the filter registry the search form is generated from
- [27_Intelligent_Ranking_Engine.md](27_Intelligent_Ranking_Engine.md) — `RankedApartmentV2`, captured via the new `SearchRunResult` field
- [30_Continuous_Monitoring.md](30_Continuous_Monitoring.md), [31_Notification_Delivery.md](31_Notification_Delivery.md) — reused by the monitoring/notification workflows
