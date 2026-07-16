# Questions

Open questions that need an answer from the user (or from research) before a decision can be made. This is a working queue, not a duplicate of the "Open Questions" sections scattered across `docs/` — when a question here gets answered, update whichever `docs/` file it blocks and remove it from this list.

- Exact structured shape for `SearchRequest.location`. Blocks: [../docs/04_Search_Request.md](../docs/04_Search_Request.md)
- Exact `status` vocabulary for availability tracking (`available`/`pending`/`delisted`/...). Blocks: [../docs/03_Data_Model.md](../docs/03_Data_Model.md)
- Should a real web-search-API provider (e.g. a licensed search API, with a vendor
  API key) be added as a third `DiscoveryProvider`, and if so which vendor? Only 2
  providers ship in v2.5 Step 13 (`curated_seed`, `manual_url`), both needing zero
  network credentials — a real search-engine-backed provider is a genuine future
  extension, not built this sprint since it needs a vendor/cost/ToS decision this
  mission didn't ask for. Blocks: [../docs/29_Automatic_Platform_Discovery.md](../docs/29_Automatic_Platform_Discovery.md)
- Who curates `discovery/automatic/normalization.py`'s `DOMAIN_ALIASES` dict (empty
  by default), and on what cadence? Real alias pairs (e.g. the same platform under a
  country-specific TLD) are a manual curation decision explicitly deferred this
  sprint. Blocks: [../docs/29_Automatic_Platform_Discovery.md](../docs/29_Automatic_Platform_Discovery.md)
- What concretely does "an explicitly approved supported API/feed integration"
  require organizationally before a `CONNECTOR_MISSING` candidate can be promoted
  without a real connector (legal review? a recorded ToS check? who signs off?) —
  `discovery-cli approve-candidate` currently lets any operator promote a candidate
  into the registry with `connector_available=False`, which is honest but doesn't
  yet enforce any approval workflow beyond "a human ran the command." Blocks: [../docs/29_Automatic_Platform_Discovery.md](../docs/29_Automatic_Platform_Discovery.md)
- Which additional notification channel (Slack, Teams, Telegram, Discord, SMS,
  mobile push) should be built next? The channel plugin system supports adding
  one with zero `NotificationEngine` changes, but none beyond Console/File/Email/
  Webhook ship in v2.5 Step 15 — needs a vendor/cost/ToS decision this mission
  didn't ask for. Blocks: [../docs/31_Notification_Delivery.md](../docs/31_Notification_Delivery.md)
- Should digest grouping eventually span multiple saved searches into one
  combined email per profile, rather than one digest per (preference, period)?
  Today each `NotificationPreference` produces its own separate digest even when
  a profile has several preferences — fine for one saved search per profile, but
  a profile monitoring many saved searches might prefer a single consolidated
  digest. Blocks: [../docs/31_Notification_Delivery.md](../docs/31_Notification_Delivery.md)
- What should `NotificationPolicy`'s production defaults be (`retry_max_attempts`,
  backoff base/max, `dead_letter_after_attempts`) once delivery runs somewhere
  other than a manually-triggered CLI — a future worker service or scheduled
  deployment decision, not answered by this sprint. Blocks: [../docs/31_Notification_Delivery.md](../docs/31_Notification_Delivery.md)
- Does `SavedSearchVersion.geographic_destinations` need a richer structured shape
  than "a list of `{country, region, city}` dicts"? Only the first entry is used
  today (`_refresh_discovery()` reads `geographic_destinations[0]`) — fine for a
  saved search monitoring one metro area, but multi-destination saved searches
  would need every entry actually consulted. Blocks: [../docs/30_Continuous_Monitoring.md](../docs/30_Continuous_Monitoring.md)
- What should `MonitoringConfiguration`'s production defaults be (`default_claim_ttl_
  minutes`, `default_worker_id`, a real production `MonitoringPolicy`) once this
  runs somewhere other than a manually-triggered CLI — a future worker service or
  scheduled deployment decision, not answered by this sprint. Blocks: [../docs/30_Continuous_Monitoring.md](../docs/30_Continuous_Monitoring.md)

## Answered

- ~~Which delivery channel(s) should be built first for Continuous Monitoring's
  `MonitoringEvent`s, and with what per-user delivery preferences?~~
  **Console + File (zero credentials) and Email + Webhook (configurable): v2.5
  Step 15** (2026-07-16) — a full `NotificationEngine` with versioned per-profile/
  per-saved-search preferences, deterministic eligibility, quiet hours, rate
  limiting, immediate-vs-digest routing, and idempotent retries. SMS/mobile push/
  a web dashboard remain open — see above. See
  [../docs/31_Notification_Delivery.md](../docs/31_Notification_Delivery.md).
- ~~When should continuous monitoring (periodic re-discovery) and notifications be
  scheduled?~~ **Continuous monitoring itself: v2.5 Step 14** (2026-07-16) — a
  database-backed scheduling/claim interface (`due_saved_searches()`/
  `claim_due_run()`/`mark_run_*()`) that any of cron, Windows Task Scheduler, a
  future worker service, or manual CLI execution can drive; **notification
  delivery itself: v2.5 Step 15** (2026-07-16) — `scheduling.next_delivery_time()`/
  `next_digest_time()`/`task_scheduler_command_examples()`, the same
  driver-agnostic shape. See
  [../docs/30_Continuous_Monitoring.md](../docs/30_Continuous_Monitoring.md),
  [../docs/31_Notification_Delivery.md](../docs/31_Notification_Delivery.md).

- ~~Which platform/data source should the first connector target?~~ **RentCast**
  (2026-07-15) — a real, developer-facing REST API with self-service auth, a free
  tier, and published Terms of Use permitting this kind of programmatic access;
  verified by live lookup rather than chosen from the 6 previously-catalogued
  scraping-prohibited platforms (Zillow, Apartments.com, Rightmove, Idealista,
  Fotocasa, ImmoScout24), all of which remain `connector_available = False`. See
  [../docs/20_First_Production_Connector.md](../docs/20_First_Production_Connector.md).
- ~~What rental type(s) does the agent need to support?~~ **Residential apartments** (2026-07-13). See [../docs/00_Project_Vision.md](../docs/00_Project_Vision.md), [../docs/03_Data_Model.md](../docs/03_Data_Model.md).
- ~~What output format does a report need?~~ **HTML only for V1.0**, since structured data already lives durably in SQLite regardless (2026-07-14). See [../docs/09_Report_System.md](../docs/09_Report_System.md).
- ~~Storage format: JSON files vs. database?~~ **SQLite** (2026-07-14). See [../learning/database_notes.md](../learning/database_notes.md).
- ~~Should `data/rental_intelligence.db`/`data/media/`/`data/raw_pages/` be gitignored or committed?~~ **Gitignored**, same treatment as `output/*` — generated artifacts, not source-controlled inputs (2026-07-14). See `.gitignore`.
