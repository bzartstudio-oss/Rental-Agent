# 46 — Version 2.7 Planning

**Status: PROPOSED (2026-07-18).** Written after confirming Version 2.6.0 is
deployed to production (Render, `https://rental-agent-web.onrender.com`,
commit `7068a0f8fc2c1f23425216bf081869b72a0e2082`) and verified — homepage
functional, health endpoint HTTP 200, persistent storage mounted at
`/data`, no secrets exposed, no blocking defect. This document proposes
scope only — no production code is written or changed by it. Implementation
happens on `feature/v2.7`, milestone by milestone, after this plan is
reviewed.

Grounded in: `docs/10_Roadmap.md`, `notes/Questions.md`, `MASTER_SPEC.md`
(Sections 43-46), `docs/45_Deployment_Guide.md`, and direct inspection of
the current codebase and the live production deployment performed during
this planning pass (see Section 2 — every finding below traces to a real
file, a real log line, or a real observed production response, not a
guess).

## 1. Version 2.7 Objective

Version 2.6 proved the platform deploys and runs safely in production.
Version 2.7's objective is narrower and more concrete: **make the one real,
ToS-compliant connector this platform already has (RentCast) actually
reachable and reliable in that production deployment**, and close the
small number of operational gaps (scheduling, rate-limit handling) that
stand between "deployed" and "useful with real data" — without redesigning
any engine, without picking a new commercial platform, and without
starting anything the user hasn't explicitly approved (paid services,
credentials, Chromium).

## 2. Findings From Direct Inspection

Each item below was verified against real code or a real production
response during this planning pass — not inferred from documentation
alone.

1. **The production web app never seeds the platform registry.**
   `DiscoveryAgent.sync_platforms(ALL_KNOWN_PLATFORMS)` — which registers
   `demo_platform`, `demo_platform_two`, and `rentcast` as
   connector-available — is called only by `src/ui/cli.py` (line 130) and
   `src/web/facade.py`'s single-candidate approval path. `src/web/application.py::create_app()`
   never calls it. Confirmed live: the production dashboard's "New Search"
   form currently reads "No connector-available platforms registered
   yet." and a real search submitted through it queries zero connectors,
   because this production deployment has only ever run the web server,
   never the CLI. This is the single highest-value fix in this plan — it
   is why RentCast (already built, already registered in code) has never
   actually run against production traffic.
2. **RentCast (`src/connectors/rentcast/`) is real, complete, and
   ToS-verified** (`docs/20_First_Production_Connector.md`) — a working
   HTTP connector requiring only `RENTCAST_API_KEY` (already wired as an
   optional, `sync: false` env var in `render.yaml`). No new connector
   code is needed to get real rental data; Finding 1 above is what's
   blocking it.
3. **`RentCastClient` (`src/connectors/rentcast/client.py`) has no
   distinct handling for HTTP 429 (rate-limit exceeded).** It retries
   connection errors/timeouts/5xx with backoff and fails immediately on
   401, but a 429 falls into the generic `raise_for_status()` path —
   treated as a hard failure, not distinguished from "temporarily out of
   quota, back off and/or stop for this run." Combined with
   `ProviderConfiguration.rate_limit_per_minute` being declared but never
   enforced (open since the Production Readiness Review, `docs/23` Q5 —
   still true today, confirmed by grep), a search that fans out to
   RentCast has no defense against burning the free tier's 50
   requests/month in one broad query beyond the existing conservative
   `_PAGE_SIZE`/`_MAX_PAGES` pagination caps.
4. **Scheduled/unattended monitoring has a real scheduling interface
   (`src/monitoring/scheduling.py`: `due_saved_searches()`,
   `claim_due_run()`, `mark_run_*()`) but nothing drives it in
   production.** `notes/Questions.md` already logs this as open
   ("what should drive this — cron, Task Scheduler, a worker"). The
   deployment work for Version 2.6 additionally established a concrete
   platform constraint: Render cannot share a persistent Disk between the
   web service and a separate Cron Job service, so an external Render Cron
   Job cannot see the same SQLite database this app writes to.
5. **RentCast's own API has no photo/image field** — confirmed in
   `RentCastConnector` (`image_urls=[]`, `supports_images=False`,
   documented inline as a verified schema fact, not an oversight). The
   *listing source link* (`RawListing.url`) is populated by every
   connector including RentCast, so "click through to the original
   listing" already works; only images are unavailable, and only for
   RentCast.
6. **Cross-platform deduplication (`apartments.merged_into_id`) remains
   entirely unbuilt** — reserved since v1.1, explicitly deferred at every
   subsequent version. With only one real connector active, there is
   nothing to deduplicate *across platforms* yet; this only becomes
   materially useful once a second real connector exists.
7. **Email and webhook notification channels are already fully built**
   (`src/notifications/channels/email_channel.py`,
   `webhook_channel.py`, v2.5 Step 15) — disabled only because no SMTP or
   webhook credentials are configured yet. This is a credentials gap, not
   an engineering gap; it needs no new code, only a verification
   procedure once the user supplies real values.
8. **Listing freshness (`last_seen_at`) is already displayed** in the
   apartment detail, comparison, and search-results templates. The real
   gap is re-observation cadence — addressed by Finding 4 (scheduling),
   not by new display logic.
9. **No external observability/error-tracking service is integrated.**
   Structured JSON logging (`src/utils/logging.py`) and the existing
   `/api/v1/health` endpoint are the only production visibility today;
   Render's own dashboard provides logs and basic metrics on top of that.
10. **Chromium is not installed in the production image** (see the
    Version 2.6 production verification report) — confirmed to block
    nothing currently reachable in production, since `demo_platform`/
    `demo_platform_two` (the only connectors that need it) are reference/
    test fixtures, not real data sources, and per user instruction this
    stays undecided, not implemented, this version.

## 3. Proposed Version 2.7 Milestones

- **Milestone 2.7.1 — Platform Registry Activation.** Make `create_app()`
  call `DiscoveryAgent.sync_platforms(ALL_KNOWN_PLATFORMS)` once at
  startup, the same idempotent call `ui/cli.py` already makes on every
  run. Directly resolves Finding 1. This is the milestone that turns
  "RentCast is built" into "RentCast is reachable in production."
- **Milestone 2.7.2 — RentCast Resilience.** Add explicit 429 handling to
  `RentCastClient` (respecting a `Retry-After` header when present,
  distinct failure category from a 5xx or 401) and a lightweight
  call-budget guard so one search cannot silently exhaust the free tier's
  monthly quota. Resolves Finding 3.
- **Milestone 2.7.3 — In-Process Scheduled Monitoring.** A background
  scheduler thread inside the existing Flask/waitress process (mirroring
  `JobRunner`'s established `threading.Thread` pattern) that periodically
  calls `due_saved_searches()`/`claim_due_run()` and runs the monitoring
  workflow for due saved searches — off by default, opt-in via a new
  `WEB_ENABLE_SCHEDULER` env var, same convention as `WEB_ALLOW_NETWORK`.
  Runs in the same process and against the same `/data` disk as the web
  app, so it sidesteps the Render cross-service-disk limitation entirely
  rather than requiring a second Render service. Resolves Finding 4.
- **Milestone 2.7.4 — Notification Delivery Verification.** No new
  source code. A documented, followable procedure (extending
  `docs/45_Deployment_Guide.md`) for the user to configure real SMTP/
  webhook credentials in the Render dashboard and confirm end-to-end
  delivery, without ever committing a real secret. Resolves Finding 7.
- **Milestone 2.7.5 — Images/Source-Link Limitation Write-Up.** Research
  only: confirm (via RentCast's published API documentation, not
  guesswork) whether any RentCast tier exposes photos; document the
  answer either way in `docs/20_First_Production_Connector.md`. No code
  change is committed by this milestone regardless of the finding — a
  follow-up milestone would be scoped separately if the finding justifies
  one.
- **Milestone 2.7.6 (optional) — Cross-Platform Deduplication Design.**
  Write the design (matching logic, confidence scoring, what populates
  `merged_into_id`) without implementing it yet, so it's ready to build
  quickly once a second real connector makes it materially useful.
- **Milestone 2.7.7 (optional) — Production Observability Decision.**
  Evaluate whether the existing structured logs + health endpoint +
  Render's built-in dashboard are sufficient, or whether an external
  error-tracking service is worth adding. Produces a documented decision;
  implementation (if any) is a separate, future milestone requiring the
  vendor/cost approval Section 5 calls out below.
- **Milestone 2.7.8 (optional, explicitly deferred) — Chromium Decision
  Record.** Document the image-size/build-time/Render-plan cost of adding
  Chromium so `demo_platform`/`demo_platform_two` (or a future
  scraping-based connector) could run in production too. No Dockerfile
  change this version, per explicit instruction.

## 4. Required vs. Optional Scope

**Required (this version):**
- 2.7.1 — Platform Registry Activation
- 2.7.2 — RentCast Resilience
- 2.7.3 — In-Process Scheduled Monitoring
- 2.7.4 — Notification Delivery Verification

**Optional (propose now, build only if approved separately):**
- 2.7.5 — Images/Source-Link Limitation Write-Up (low effort, research-only — recommended even though optional)
- 2.7.6 — Cross-Platform Deduplication Design (design-only; implementation is a future version)
- 2.7.7 — Production Observability Decision (decision-only; any paid tool needs its own approval)
- 2.7.8 — Chromium Decision Record (record-only; explicitly not implemented this version)

## 5. Third-Party Dependencies and Likely Costs

| Item | Vendor | Cost | Status |
|---|---|---|---|
| RentCast API | RentCast | **Free tier**: 50 requests/month, no card required at signup (per `docs/20_First_Production_Connector.md`, verified at the time RentCast was chosen). Paid tiers exist for higher volume — not needed for 2.7.1/2.7.2. | Required (already integrated; only the key is missing) |
| SMTP provider (for email notifications) | User's choice (Gmail, SendGrid, etc.) | Varies; many have a free tier sufficient for personal-scale alerting | Optional, user-owned |
| Webhook target | User's choice (Slack incoming webhook, custom endpoint, etc.) | Free in the common case | Optional, user-owned |
| Error-tracking service (if 2.7.7 concludes one is worth adding) | Not yet chosen (e.g. Sentry) | Most have a free tier at this project's scale; a paid tier would only be needed at higher volume | Optional, **not committed this version** |
| A second real rental-platform connector | Not applicable | Blocked by ToS for all 6 previously-catalogued candidates (Zillow, Apartments.com, Rightmove, Idealista, Fotocasa, ImmoScout24) — unchanged since `docs/10_Roadmap.md`; needs a business/legal decision, not an engineering one | Out of scope, unresolved from prior versions |

Render's own hosting cost (the `starter` plan + 1 GB disk, already running)
is unchanged by this plan — no new Render resources are proposed.

## 6. Credentials the User Will Eventually Need

- **`RENTCAST_API_KEY`** — required to make Milestone 2.7.1 actually
  produce real listings in production (the milestone itself works with
  zero key configured too — it correctly reports RentCast as
  connector-available but currently unauthenticated, exactly like the
  local-dev behavior already documented). Sign up at
  [rentcast.io](https://www.rentcast.io), free tier, no card required at
  signup per the prior verification.
- **SMTP credentials** (host, username, password, sender/recipient) —
  only if the user wants Milestone 2.7.4's email channel verified against
  a real mailbox. Already-documented env vars in `.env.example`.
- **A webhook URL and optional signing secret** — only if the user wants
  Milestone 2.7.4's webhook channel verified against a real endpoint
  (e.g. a Slack incoming webhook URL). Already-documented env vars.
- **No credential is required to ship Milestones 2.7.1–2.7.3** —
  2.7.1 and 2.7.3 work with zero configuration (same "empty" behavior the
  platform has always had); only *exercising* real RentCast data or real
  notification delivery needs the credentials above.

I will never enter, request the value of, or commit any of these
credentials — the user configures them directly in the Render dashboard's
environment variables, same as `WEB_SECRET_KEY` already is.

## 7. Architectural Impact

Minimal. 2.7.1 is a one-line addition to `create_app()`'s startup
sequence calling an existing, already-idempotent function. 2.7.2 extends
`RentCastClient`'s existing status-code branching with one more case — no
new module. 2.7.3 adds one new small module (`src/web/scheduler.py` or
similar) reusing `MonitoringEngine`/`scheduling.py` exactly as published,
mirroring `JobRunner`'s existing threading pattern — no new engine, no
change to any engine's public contract. 2.7.4 and 2.7.5 are documentation
only. No existing route, template, CLI flag, or public function signature
changes for any required milestone.

## 8. Database and Migration Impact

None for any required milestone (2.7.1–2.7.4). 2.7.1 only calls an
existing write path (`sync_platforms`) against the existing `platforms`
table. 2.7.2 changes only in-memory retry/backoff logic. 2.7.3 reuses
`monitoring_schedules`/`monitoring_runs`, both already migrated (v2.5 Step
14) with the atomic claim mechanism this milestone needs already built
in. If Milestone 2.7.6 (optional, design-only) is later implemented, it
would need its own migration for whatever match/confidence table the
design specifies — not scoped or committed here.

## 9. Security Considerations

- 2.7.1 introduces no new trust boundary — it seeds already-public,
  already-reviewed platform metadata (`known_platforms.py`), the same
  data the CLI has written to every local database since v1.1.
- 2.7.2 must continue the existing discipline of never logging the API
  key itself (already true today — `RentCastClient` logs `path`/
  `attempt`/`status_code`, never headers).
- 2.7.3's scheduler must run under the same `profile_id`/permission model
  every other automated write in this codebase already uses — it must
  not introduce a new, unauthenticated code path; it calls the same
  `MonitoringEngine` a manual "Run Now" click already calls.
- 2.7.4 is documentation-only; it must reinforce, not weaken, the
  existing `_redact()`/no-secret-in-logs discipline already built into
  both notification channels.

## 10. Testing Strategy

Unchanged discipline from every prior version: every new behavior gets a
real, deterministic test (unittest, no live network) before being
considered done.

- **2.7.1**: a test asserting `create_app()` (fresh in-memory/temp
  database, no prior CLI run) results in `demo_platform`,
  `demo_platform_two`, and `rentcast` all reporting
  `connector_available=True` via the same facade call the search form
  uses — reproducing, and then closing, the exact production gap found
  in Section 2. A regression test confirming `sync_platforms` is
  idempotent when called against a database that already has these rows
  (must not duplicate or error).
- **2.7.2**: unit tests driving `RentCastClient` against a fake transport
  returning 429 with and without a `Retry-After` header, confirming
  distinct handling from 401/5xx; a test confirming the call-budget guard
  stops before exceeding a configured request ceiling within one search,
  surfacing a clear, non-crashing result rather than an exception.
- **2.7.3**: a real (not mocked at the scheduler level) test that seeds a
  due saved search, runs the scheduler loop once with a fast-forwarded
  clock, and confirms a real `monitoring_runs` row and any resulting
  `monitoring_events` are written — mirroring
  `tests/acceptance/test_journey_c_saved_search_monitoring.py`'s existing
  shape. A test confirming the scheduler is inert when
  `WEB_ENABLE_SCHEDULER` is unset (default, matching every existing
  opt-in flag's tested-off-by-default convention).
- **2.7.4**: no new automated test (documentation-only); the acceptance
  criterion is a human-followable procedure, verified by a dry run
  against a real but disposable SMTP/webhook target during
  implementation, not committed as a permanent test.
- **2.7.5**: no automated test; a documented finding.

Full suite must stay green throughout (starting baseline: 1344 tests, all
passing, confirmed at the Version 2.6.0 promotion — see `docs/42_Version_2.6_Acceptance_Report.md`),
plus `scripts/health_check.py` unchanged at 10 PASS/2 WARN/1 FAIL (the
`playwright_browsers` FAIL remains expected and untouched by this plan;
see Milestone 2.7.8).

## 11. Backward-Compatibility Requirements

- 2.7.1 must not change behavior for any existing CLI caller —
  `create_app()` calling `sync_platforms` is additive to the web path
  only; the CLI's own already-idempotent call is unaffected either way.
- 2.7.2's new 429 handling must not change behavior for any
  already-passing 401/5xx/timeout test — only a genuinely new
  status-code branch is added.
- 2.7.3 must be fully inert (zero behavior change) when
  `WEB_ENABLE_SCHEDULER` is unset, preserving today's exact production
  behavior for any deployment that doesn't opt in.
- No existing route, CLI flag, template, or database column is removed
  or renamed by any required milestone.

## 12. Branch and Release Strategy

- **`main` remains the production branch**, deploying automatically to
  Render on every push, exactly as configured today.
- **`v2.6.0` remains the current rollback release** — untouched, still
  tagged, still deployed until a Version 2.7 release is explicitly
  promoted the same deliberate way v2.6.0 was (backup branch before any
  history rewrite, fast-forward-only merges, full suite + health check
  before tagging).
- **All Version 2.7 implementation happens on `feature/v2.7`** (this
  branch), milestone by milestone, each with its own commit and its own
  full-suite run — the same discipline `feature/v2.6` followed.
- **No merge into `main` and no Render deployment happens as part of
  planning or of any individual milestone landing on `feature/v2.7`** —
  promotion to `main` is a separate, explicit, future step requiring its
  own review, exactly like the Version 2.6 promotion procedure.
- If any required milestone needs to ship independently before the
  others are ready, it can be cut from `feature/v2.7` into its own
  short-lived branch and merged to `main` on its own — nothing in this
  plan requires all four required milestones to land in one release.

## 13. Recommended Implementation Order

1. **2.7.1 (Platform Registry Activation)** — smallest, safest, highest
   value; every other required milestone is more useful once this lands,
   since it's what makes RentCast reachable at all.
2. **2.7.2 (RentCast Resilience)** — directly follows 2.7.1; hardens the
   connector 2.7.1 just made reachable, before real traffic hits it.
3. **2.7.4 (Notification Delivery Verification)** — documentation-only,
   independent of the others, low risk, can land any time.
4. **2.7.3 (In-Process Scheduled Monitoring)** — largest required
   milestone, benefits from 2.7.1/2.7.2 already being in place so a
   scheduled run actually has a working connector to query.
5. **2.7.5 (optional, recommended)** — research-only, no dependency,
   cheap to do whenever.
6. **2.7.6/2.7.7/2.7.8 (optional)** — design/decision records only,
   scheduled opportunistically; none block a Version 2.7 release.

## 14. Risks and Mitigations

- **Risk**: Milestone 2.7.1 could be mistaken for "now search works
  end-to-end," when a real RentCast key still needs to be configured
  separately. **Mitigation**: acceptance criteria explicitly separate
  "connector-available in the dashboard" (2.7.1's actual scope) from
  "returns real listings" (needs the user's own key) — the release notes
  for this milestone must state this distinction plainly.
- **Risk**: The in-process scheduler (2.7.3) could be over-built into a
  general task-queue replacement. **Mitigation**: scope strictly to
  calling the already-existing `scheduling.py` functions on a timer,
  reusing `JobRunner`'s established pattern — explicitly not a Celery/RQ
  migration (that remains the open `notes/Questions.md` item it already
  is).
- **Risk**: Scope creep into a second real commercial connector, given
  how closely "connector discovery and activation" reads as an
  invitation to add one. **Mitigation**: Section 2/Section 5 state
  plainly that all six previously-catalogued candidates remain
  ToS-blocked; this plan does not propose adding one, and any
  implementation PR attempting to would be out of this plan's scope.
- **Risk**: Rate-limit hardening (2.7.2) could be expanded into a full
  general-purpose rate-limiter for every provider. **Mitigation**: scope
  to RentCast's `RentCastClient` specifically — the one provider with an
  actual documented quota today; a general mechanism is future work if a
  second rate-limited provider is ever added.

## 15. Explicitly Out of Scope

- Any real commercial rental-platform connector beyond RentCast — still
  ToS-blocked for all six previously-catalogued candidates.
- Real travel-time/transit-routing integration (replacing the haversine
  estimate) — unchanged open decision from `notes/Questions.md`.
- A real task queue (Celery/RQ), multi-user authentication, or a
  general-purpose rate-limiter — all remain open, deployment-scale
  decisions logged in `notes/Questions.md`, not resolved here.
- Installing Chromium in production — explicitly deferred (Milestone
  2.7.8 is a decision record only).
- Implementing cross-platform deduplication — Milestone 2.7.6 is a
  design only.
- Adding any new notification channel beyond the four already built
  (Console/File/Email/Webhook) — still an open, vendor-dependent decision
  in `notes/Questions.md`.
- Adding or wiring any external observability/error-tracking service —
  Milestone 2.7.7 is a decision record only.

## Related Documents

- [10_Roadmap.md](10_Roadmap.md)
- [20_First_Production_Connector.md](20_First_Production_Connector.md)
- [30_Continuous_Monitoring.md](30_Continuous_Monitoring.md)
- [31_Notification_Delivery.md](31_Notification_Delivery.md)
- [41_Version_2.6_Planning.md](41_Version_2.6_Planning.md) — the
  equivalent planning document for the prior version, same structure
- [45_Deployment_Guide.md](45_Deployment_Guide.md)
- [../notes/Questions.md](../notes/Questions.md)
