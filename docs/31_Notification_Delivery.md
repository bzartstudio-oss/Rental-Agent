# 31 — Notification Delivery Engine

Version 2.5 Step 15. Monitoring (Step 14) detects change and creates
`MonitoringEvent`s; this layer separately decides whether, how, and when an
eligible event actually reaches a human, through whichever channels they
configured. It is **not** a web dashboard, SMS, mobile push, or autonomous/
marketing messaging — those stay out of scope this sprint.

## Architecture

`src/notifications/` builds entirely on top of `MonitoringEngine`'s already
-public `monitoring.service` read functions — nothing in `src/monitoring/`
changes to support this:

```
NotificationEngine.process_pending_deliveries(db) / .process_due_digests(db) / .retry_due_failures(db)
        │
        ├─ 1.  monitoring_service.get_unacknowledged_events()          (load undelivered MonitoringEvents)
        ├─ 2.  service.get_latest_preference_version()                 (resolve immutable preference version)
        ├─ 3.  eligibility.evaluate_event()                              (content: type/severity/significance/opt-in/channel)
        ├─ 4.  quiet_hours.is_in_quiet_hours() / rate_limiting.is_rate_limited()   (time-dependent, deferral-capable)
        ├─ 5.  immediate-or-digest routing (eligibility.is_immediate / .is_digest_only)
        ├─ 6.  NotificationTemplateRegistry.for_event_type() → template.render() → RenderedTemplate
        ├─ 7.  NotificationChannelFactory.resolve() → channel.send() independently, per channel
        ├─ 8.  service.record_attempt() / record_channel_health_observation()      (per-channel outcome)
        ├─ 9.  delivery.status = DELIVERED / PARTIALLY_DELIVERED / FAILED / RETRY_SCHEDULED
        └─ 10. NotificationBatch counters updated; MonitoringEvents left untouched
        │
        ▼
NotificationDelivery + NotificationAttempt history + NotificationMessage(s)
```

Every heavy piece — `MonitoringEvent` loading, apartment/report lookups for
template rendering, `FeedbackEngine` recording — is called exactly as any
other caller would; `NotificationEngine` only adds eligibility, quiet-hours/
rate-limit policy, retry/backoff, and channel orchestration on top.

## Separation From Monitoring

"Monitoring detects changes and creates events. Notification Delivery sends
eligible events through configured channels. Keep these responsibilities
completely separate" (the mission's own words), enforced two ways:

- **One-directional dependency.** `src/notifications/` imports
  `src.monitoring.service`'s public read functions only — it never imports
  `MonitoringEngine`, never reaches into monitoring's internals, and never
  writes to a `monitoring_*` table. `src/monitoring/` has zero imports from
  `src/notifications/` at all; monitoring must build and run identically
  whether the notifications package exists or not.
- **Failure isolation is bidirectional.** A `MonitoringEvent` is never
  modified by delivery — not even `acknowledged`, which only
  `MonitoringEngine.acknowledge_event()`/`NotificationEngine.acknowledge()`'s
  own `notification_deliveries.acknowledged` flag ever flips, and they are
  two different flags on two different rows. A notification failure (a dead
  SMTP server, an unreachable webhook) can never fail, retry, or block a
  monitoring run — `MonitoringEngine.run_now()`/`run_due()` never calls into
  `src/notifications/` at all; delivery is a wholly separate, later step a
  caller (the CLI, a scheduler) triggers on its own.

## Channel Plugin System

`NotificationChannel` (`base_channel.py`, ABC) mirrors
`connectors.sdk.BaseConnector`'s "one shared template, small platform-
specific hooks" shape: every channel implements `configure()`,
`validate_configuration()`, `supports(capability)`, `preview(message)`,
`send(message)`, `channel_info()`; `send_batch()`/`serialize_result()`/
`health_check()`/`is_enabled()` are provided by the base class and rarely
overridden. `is_enabled()` is **never** a stored flag — it is always exactly
`validate_configuration()`'s live answer, so a channel can never claim to be
enabled while genuinely misconfigured. Four channels ship this sprint, all
self-registering at import time via `channels/__init__.py`:

| Channel | `channel_name` | Enabled by default? | Notes |
|---|---|---|---|
| `ConsoleNotificationChannel` | `console` | Yes — zero credentials | Prints text or JSON preview to stdout |
| `FileNotificationChannel` | `file` | Yes — zero credentials | Writes under `output/notifications/`, never overwrites |
| `EmailNotificationChannel` | `email` | No — until `smtp_host`+`sender_address` configured | Provider-independent SMTP |
| `WebhookNotificationChannel` | `webhook` | No — until a valid `url` configured | Generic HTTP POST, HMAC-signed if a secret is set |

A future channel (Slack/Teams/Telegram/Discord/SMS/push — **not built this
sprint**) is one new module implementing `NotificationChannel` plus one
`register_notification_channel(YourChannel())` call at import time. Zero
changes to `NotificationEngine`/`NotificationChannelRegistry` are required —
`tests/notifications/test_channel_registry.py` proves this directly with a
throwaway test-only channel.

### Adding a channel

1. Subclass `NotificationChannel`, set a class-level `channel_name`.
2. Implement `configure()` (read config dict keys and/or env vars),
   `validate_configuration()` (a live, honest check — never a cached flag),
   `supports()`, `preview()` (render only, never the real side effect),
   `send()` (never raise for an ordinary delivery failure — return
   `NotificationChannelResult(success=False, error_category=...)`), and
   `channel_info()`.
3. Call `register_notification_channel(YourChannel())` at module level, and
   import that module from `channels/__init__.py`.

## Notification Preferences

`NotificationPreference` (current-state row) + `NotificationPreferenceVersion`
(append-only, one immutable row per edit — "Never overwrite preferences"
verbatim) mirrors `SavedSearch`/`SavedSearchVersion`'s exact split.
`NotificationEngine.update_preference(db, preference_id, **overrides)` always
inserts a *new* version and bumps `current_version`; a prior version stays
fully reproducible. Every field the mission names lives on the version:
`enabled_channels`, `event_types` (empty = every type eligible),
`immediate_event_types`/`digest_event_types`, `minimum_severity`/
`minimum_significance`, `digest_frequency`, `quiet_hours_start`/
`quiet_hours_end`, `timezone`, `max_per_hour`/`max_per_day`,
`include_images`/`include_original_urls`/`include_ranking_explanation`/
`include_geo_summary`/`include_preference_explanation`/`include_report_links`,
`language`/`format`, `metadata`. A preference is either scoped to one
`saved_search_id` or, when `saved_search_id` is `NULL`, applies to every
saved search belonging to that profile (`_applicable_preferences()` resolves
this by joining through `SavedSearch.profile_id`).

## Event Eligibility

`eligibility.evaluate_event()` is deterministic and explainable — "every
ineligible outcome must name its exact reason, never a bare `False`" (the
mission's own words), returned as a `NotificationEligibility` with
`ineligible_reasons: dict[channel_or_"*", reason]`. It checks, in order:
preference enabled, event not already acknowledged, `event.notification_eligible`,
opted-in `event_types`, `minimum_severity`, `minimum_significance`, then
resolves `eligible_channels` (a channel must be both listed in
`enabled_channels` *and* currently `is_enabled()` — an email channel listed
but not configured produces a per-channel `"channel is not currently
configured"` reason, never a silent drop). `explain_eligibility()`/
`eligible_channels()`/`ineligible_reasons()` expose the same result three
ways for the CLI/tests.

Quiet hours and rate limiting are **deliberately not** evaluated inside
`eligibility.py` — they are time-dependent, deferral-capable decisions the
mission's own workflow diagram lists as a separate step
("Evaluate eligibility" → "Apply quiet hours and rate limits"), applied by
`NotificationEngine` immediately after eligibility, in `quiet_hours.py`/
`rate_limiting.py`.

## Immediate vs. Digest Delivery

`eligibility.evaluate_event()` marks an event `is_immediate` (its type is in
`immediate_event_types`) or `is_digest_only` (not immediate, but a
`digest_frequency` is configured) — never both, and an event type that's in
neither list is simply ineligible. `immediate_event_types` is a configurable
list per preference, never hardcoded to "every event type" — a preference
with `immediate_event_types=[]` and a `digest_frequency` set receives nothing
immediately and everything through its next digest.

**Immediate**: `process_pending_deliveries()` handles one event at a time,
one `NotificationDelivery` per (preference, event) pair, `idempotency_key =
f"{preference_id}:{event_id}"`.

**Digest**: `process_due_digests()` (scheduler-driven, checks
`scheduling.is_digest_due()` per preference) and `generate_digest()` (manual,
bypasses the due-time check) both call the shared `_generate_one_digest()`:
groups every eligible digest-only event since the last digest's
`period_end` (or `now - lookback` for the first digest) by saved search,
resolves channels once for the whole group, renders one digest template, and
links exactly the included events to the delivery via
`notification_delivery_events` (the same link table every delivery, immediate
or digest, uses) — an event already linked to one delivery is never included
in a later digest (`_events_in_window()` checks
`service.get_delivery_ids_for_event()` before adding a candidate), giving
reproducible, non-overlapping digest membership.

## Message Model & Templates

`NotificationMessage` is the one channel-neutral shape every channel's
`send()`/`preview()` receives — `notification_id`, `delivery_id`,
`profile_id`, `event_ids`, `channel`, `subject`/`body_text`/`body_html`,
`original_listing_urls`, `report_links`, `template_name`/`template_version`,
`language`, `generated_at`, `metadata`. Reproducible: the same
`template_name`/`template_version` plus the same stored `MonitoringEvent`
context always renders the same output (`tests/notifications/test_templates.py
::test_rendering_is_reproducible_for_the_same_inputs`).

`NotificationTemplate` (ABC, `base_template.py`) mirrors `NotificationChannel`'s
self-registration shape: `render(TemplateContext) -> RenderedTemplate`. Eight
ship this sprint, self-registering via `templates/__init__.py`:

- **6 immediate alert templates**, one shared base (`_EventAlertTemplate` in
  `event_alert_templates.py`) since they differ only in subject framing and
  matched event types: `immediate_apartment_alert` (NEW_MATCH/NEW_LISTING),
  `price_change_alert`, `availability_alert`, `better_match_alert`,
  `listing_removal_alert`, `monitoring_failure_alert`.
- **2 digest templates**, one shared base (`_DigestTemplate` in
  `digest_templates.py`): `daily_digest`/`weekly_digest` — group by saved
  search, sections for top new matches (ordered by significance)/price
  changes/availability changes/ranking changes/failed platforms, original
  URLs and report links de-duplicated across the whole digest. Hourly and
  manual digests reuse `daily_digest`'s own rendering (`_digest_template_for_
  frequency()` in `engine.py`) — only `context.frequency`'s label differs, so
  no third/fourth template class exists.

`templates/helpers.py` (`apartment_for_event`/`apartment_image_paths`/
`report_links_for_run`) is the *only* way a template reads apartment/report
data — "Do not duplicate complete report generation logic" (the mission's own
words): templates link to already-generated monitoring report files
(`monitoring_service.get_report_artifacts_for_run()`), never regenerate one.

### Adding a template

1. Subclass `NotificationTemplate`, set `template_name`, `version`, and
   `event_types` (empty for a digest/catch-all template).
2. Implement `render(context) -> RenderedTemplate`.
3. Call `register_notification_template(YourTemplate())` at module level, and
   import that module from `templates/__init__.py`.

No change to `NotificationEngine`/`NotificationTemplateRegistry` is required.

## Retry Policy & Idempotency

`NotificationPolicy` (`retry_max_attempts`, `retry_backoff_base_seconds`,
`retry_backoff_max_seconds`, `retryable_error_categories`,
`non_retryable_error_categories`, `dead_letter_after_attempts`) is an
engine-level deployment knob, distinct from per-preference settings — the
same "deployment knob vs. per-item policy" split `MonitoringConfiguration
.default_policy`/`MonitoringPolicy` already made. `retry.compute_next_attempt_at()`
is exponential backoff capped at `retry_backoff_max_seconds`;
`retry.should_dead_letter()` moves a delivery to `FAILED` (no further
`next_attempt_at`) once `attempt_count` reaches `dead_letter_after_attempts`.

"Retries must be idempotent. A repeated attempt must not generate a second
logical notification" (the mission's own words): `NotificationDelivery
.idempotency_key` is stable per (preference, event) or (preference, digest
period) — `retry_due_failures()`/`retry_delivery_now()` always resolve and
reuse the *same* delivery row, and only re-attempt channels absent from that
row's own "already delivered" set (computed from `NotificationAttempt.status
== "delivered"` history) — a channel that already succeeded is never
re-sent. `get_due_retries()` selects both `RETRY_SCHEDULED` and
`PARTIALLY_DELIVERED` deliveries, since a partial delivery still has failed
channels worth retrying.

## Rate Limiting

`rate_limiting.is_rate_limited()` checks `count_rate_limit_observations_since()`
against `max_per_hour`/`max_per_day` from the preference version, per
(profile, channel) pair. A rate-limited channel is never silently dropped —
"Rate-limit suppression must be stored and explainable" (the mission's own
words): the delivery is recorded as `SUPPRESSED` with a `notes` string
explaining why (`"Suppressed: rate limit reached for every eligible
channel"`), and the underlying `MonitoringEvent` remains fully eligible for a
later digest.

## Quiet Hours

`quiet_hours.is_in_quiet_hours()`/`next_permitted_time()` are timezone-aware
(`zoneinfo.ZoneInfo(preference_version.timezone)`), correctly handling both
same-day (`"09:00"`-`"17:00"`) and midnight-wrapping (`"22:00"`-`"07:00"`)
windows. A non-critical event during quiet hours is deferred, not dropped:
the delivery is recorded `SUPPRESSED` with `next_attempt_at =
next_permitted_time(...)` and `notes = "Deferred: quiet hours"`. A `critical`
-severity event bypasses quiet hours entirely — "urgent events only if
preference permits" is satisfied by severity always taking precedence,
matching the mission's own examples (a `MONITORING_RUN_FAILED` event should
still reach someone at 3 AM).

## Acknowledgement

`NotificationEngine.acknowledge(db, delivery_id, acknowledged_by=None,
note=None)` flips `notification_deliveries.acknowledged` and appends one row
to `notification_acknowledgements` (append-only audit trail — never deletes
delivery/attempt/event history). Acknowledging a delivery is a separate,
explicit action from acknowledging the underlying `MonitoringEvent` — the two
`acknowledged` flags never influence each other automatically.

## Database

Migration `0010_notification_delivery.sql` — 12 new tables, every prior
migration (0001–0009) completely untouched: `notification_preferences`/
`notification_batches`/`notification_deliveries` (current-state, one mutation
function each, mirroring `saved_searches`/`monitoring_runs`),
`notification_preference_versions` (append-only, one immutable row per edit),
`notification_templates` (append-only registry snapshot), `notification_
delivery_events`/`notification_digests`/`notification_attempts`/
`notification_messages`/`rate_limit_observations`/`channel_health_
observations`/`notification_acknowledgements` (strictly append-only). See
[03_Data_Model.md](03_Data_Model.md) for the full column-by-column reference.

## Monitoring Integration

`NotificationEngine` consumes `MonitoringEvent`s exclusively through
`monitoring.service`'s public read functions (`get_unacknowledged_events()`,
`get_event()`, `get_events_for_saved_search()`, `get_saved_search()`,
`get_report_artifacts_for_run()`) — it never imports `MonitoringEngine`
itself, and never writes to any `monitoring_*` table. Monitoring runs
identically whether the notifications package is absent, mid-outage, or
fully configured; a notification failure never fails, retries, or blocks a
monitoring run.

## Feedback Integration

`feedback_integration.record_user_reaction(conn, feedback_engine, profile_id,
delivery_id, reaction, occurred_at)` is the *only* path from a delivered
notification to a `FeedbackEvent`, and it is **never** called automatically
by `process_pending_deliveries()`/`process_due_digests()` — "Do not infer
preference merely because a notification was delivered" (the mission's own
words). Only an explicit, named reaction (`notification_opened`/
`original_listing_opened`/`dismissed`/`saved`/`rejected`, mapped to
`FeedbackEventType` constants — two new ones, `NOTIFICATION_OPENED`/
`NOTIFICATION_DISMISSED`, added to `src/feedback/event_types.py` this sprint)
produces feedback evidence, triggered via `notification-cli
acknowledge-notification --reaction ... --profile-id ...`.

## Report Integration

Templates link to already-generated monitoring report files
(`report_links_for_run()`) and to the apartment's own `url`/image paths —
never a second report-generation implementation. Ranking explanation/geo
summary/preference-match explanation are exposed to templates only insofar
as `MonitoringEvent.evidence`/`explanation` (already computed by monitoring's
own detectors) already carries them; nothing here recomputes analysis,
ranking, or geo output.

## Security & Privacy

- **Secrets never logged.** `EmailNotificationChannel._redact()`/
  `WebhookNotificationChannel._redact()` strip the configured
  password/signing-secret out of any exception text before it is stored in
  `NotificationAttempt.error`/`ChannelHealthObservation.error` or returned
  from `send()`. `serialize_result()`/`channel_info()` never echo `self._config`.
- **No file-channel path traversal.** `FileNotificationChannel._resolve_path()`
  builds filenames only from controlled components (`delivery_id` UUID +
  integer `attempt_number` + channel name — never freeform subject/body
  content) and asserts the resolved path stays inside the configured output
  directory as defense in depth.
- **Webhook domain allow/deny lists.** `WebhookNotificationChannel
  ._is_url_allowed()` requires an `http`/`https` scheme and checks the
  destination hostname against `denied_domains` (checked first) and, if set,
  `allowed_domains`.
- **No notifications without explicit opt-in.** An event with no matching
  `NotificationPreference` for its profile produces zero deliveries to
  anyone — `_applicable_preferences()` only ever matches preferences that
  already exist; there is no default/fallback preference.
- **Idempotency keys, not secrets, identify a webhook delivery.** Every
  webhook POST carries an `Idempotency-Key` header equal to `delivery_id`
  (a UUID, not a credential) so a receiving endpoint can de-duplicate a
  retried delivery safely.

## CLI

`src/ui/notification_cli.py` (a fifth, thin entry point alongside `ui/cli.py`/
`ui/feedback_cli.py`/`ui/discovery_cli.py`/`ui/monitoring_cli.py`):
`create-preference`, `list-preferences`, `view-preference`,
`update-preference` (creates a new version), `enable-notifications`/
`disable-notifications`, `preview-notification`, `send-test-notification`,
`deliver-pending`, `generate-digest` (one preference, or every due preference
via `process_due_digests()` when `--preference-id` is omitted), `retry-due`,
`list-deliveries`, `list-failed-deliveries`, `retry-delivery`,
`cancel-delivery`, `acknowledge-notification` (optionally with
`--reaction`/`--profile-id`), `channel-health`, `statistics`,
`export-history`, `task-scheduler-examples`.

## Scheduler Interface

`src/notifications/scheduling.py` — `next_digest_time()`, `is_digest_due()`,
`next_delivery_time()`, `task_scheduler_command_examples()`. Nothing here
loops or sleeps — each is a single, idempotent database read a caller
invokes once from whatever triggers it; `process_pending_deliveries()`/
`process_due_digests()`/`retry_due_failures()` themselves live on
`NotificationEngine` (they need the full engine to actually deliver).
"Do not implement an operating-system-specific daemon" (the mission's own
words):

```
cron_deliver:            */5 * * * * cd /path/to/project && python -m src.ui.notification_cli deliver-pending
cron_digest:              0 8 * * * cd /path/to/project && python -m src.ui.notification_cli generate-digest --frequency daily
windows_task_scheduler:   schtasks /create /tn "NotificationDelivery" /tr "python -m src.ui.notification_cli deliver-pending" /sc minute /mo 5
manual_cli:                python -m src.ui.notification_cli deliver-pending
```

`notification_cli.py`, like every other CLI in this project, always opens
`src.core.config.DB_PATH` — there is no `--db-path` override flag, so the
examples don't invent one.

## Email Configuration

`EmailNotificationChannel` reads, in order, a config dict key then an
environment variable: `smtp_host`/`SMTP_HOST`, `smtp_port`/`SMTP_PORT`
(default `587`), `smtp_username`/`SMTP_USERNAME`, `smtp_password`/
`SMTP_PASSWORD`, `sender_address`/`SMTP_SENDER`, `recipient_address`/
`SMTP_RECIPIENT` (a message's own `metadata["recipient"]` overrides this
default per-send), `use_tls`/`SMTP_USE_TLS` (default `true`), `use_ssl`/
`SMTP_USE_SSL` (default `false`), `timeout`/`SMTP_TIMEOUT` (default `10.0`
seconds). `validate_configuration()` is `bool(host and sender)` — disabled
until both are set. Delivery goes through `EmailTransport` (a `Protocol`),
with `SmtplibEmailTransport` the one real implementation — the same
injectable-seam shape `discovery.automatic.verification.PageFetcher`
established, specifically so the test suite never opens a real SMTP
connection.

## Webhook Configuration

`WebhookNotificationChannel` reads `url`/`WEBHOOK_URL`, optional `headers`
dict, `timeout` (default `10.0` seconds), `signing_secret`/
`WEBHOOK_SIGNING_SECRET` (HMAC-SHA256, sent as `X-Signature-256:
sha256=<hex>`), `allowed_domains`/`denied_domains` lists. `validate_
configuration()` requires both a non-empty `url` *and* that URL passing the
domain allow/deny check. Delivery goes through `HttpTransport` (a
`Protocol`), with `UrllibHttpTransport` the one real implementation — same
injectable-seam shape as email, so the test suite never sends a request to a
real endpoint.

## Console / File Channels

`ConsoleNotificationChannel` prints a preview to stdout in `"text"` (default)
or `"json"` mode — always enabled, zero configuration. `FileNotificationChannel`
writes under `output/notifications/` (overridable via `output_dir`) in
`"text"` (default), `"html"`, or `"json"` format, filename
`f"{delivery_id}__attempt-{attempt_number}__{channel}.{extension}"` —
deterministic and collision-free across retries, preserving full delivery
history; a filename collision (the same delivery/attempt/channel tuple asked
to send twice) is refused rather than silently overwritten.

## Troubleshooting

- **A configured Email/Webhook preference shows "channel is not currently
  configured" in eligibility reasons.** `validate_configuration()` is a live
  check — verify the exact config keys/env vars above are actually set for
  *this process*, not just recorded somewhere else. Run `notification-cli
  channel-health --channel email` to see recent send history for that
  channel specifically.
- **A digest never generates.** Check `scheduling.is_digest_due()` — the
  first digest for a brand-new preference is always immediately due; every
  digest after that is due only once `period_end + <frequency interval>` has
  elapsed. `generate-digest --preference-id ...` bypasses the due-time check
  entirely for manual testing.
- **A delivery stays `RETRY_SCHEDULED` forever.** Check `attempt_count`
  against `NotificationPolicy.dead_letter_after_attempts` — once reached, the
  delivery moves to `FAILED` (no further `next_attempt_at`) rather than
  retrying indefinitely. `notification-cli list-failed-deliveries` surfaces
  these.
- **Original listing URLs are missing from a message.** Check
  `NotificationPreferenceVersion.include_original_urls` — when `False`,
  templates omit them by design, not by data-gap.

## Known SQLite Limitations

- **Digest scheduling derives "next due" from stored digest history, not a
  separate schedule table.** `next_digest_time()` computes
  `latest.period_end + interval` from the most recent
  `notification_digests` row for a preference — correct and simple at this
  scale, but means a preference whose *very first* digest is somehow delayed
  past its interval has no separate "catch-up" bookkeeping beyond "the next
  scheduler tick will find it still due."
- **Rate-limit/channel-health windows are computed by scanning
  `rate_limit_observations`/`channel_health_observations` rows directly, not
  a maintained rolling counter.** Fine at the volume a single profile's
  notification history reaches; would need a windowed aggregate or a
  separate counter table at much higher send volume.

## What's Deliberately Not Built This Sprint

Per the mission's own explicit instructions: SMS, mobile push, a web
dashboard, autonomous outbound/marketing messaging, and any channel beyond
Console/File/Email/Webhook (Slack/Teams/Telegram/Discord — the plugin system
supports adding them later with zero engine changes, but none ship now). See
[../notes/Questions.md](../notes/Questions.md) for the open product decisions
this leaves (which additional channel to build first, whether digest
grouping should eventually span multiple saved searches into one combined
email per profile, and default `NotificationPolicy` retry/backoff values for
a production deployment).
