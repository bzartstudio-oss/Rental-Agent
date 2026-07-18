# 45 — Deployment Guide

Version 2.6 deployment-readiness preparation. Everything needed to run the
Rental Intelligence Platform's web dashboard in production: the detected
architecture, the recommended host and why, the environment variables a
deployment needs, and the startup/migration/backup/rollback procedures. This
document prepares the platform for deployment — it does not itself deploy
anything (see "Status" below).

**Status: readiness only.** No hosting account has been created, no paid
resource has been provisioned, and nothing has been deployed. Everything
below is either a file in this repository (`Dockerfile`, `render.yaml`,
`.env.example`) or an instruction a human runs deliberately.

## 1. Detected Architecture

- **Framework**: Flask (`src/web/application.py::create_app()`, an app
  factory — the same one the dev server, the test suite, and production all
  call).
- **Database**: SQLite, one file (`data/rental_intelligence.db` by default).
  Single-writer-friendly, no separate database server to provision. Schema
  and every numbered migration under `src/storage/migrations/` are applied
  automatically the first time `Database()` is constructed — see [§4](#4-migrations).
- **Background work**: on-demand only. Search/monitoring/discovery runs are
  spawned as a `threading.Thread` inside the same process, triggered by a
  user action in the dashboard (`src/web/jobs/runner.py`) — there is no
  separate always-running worker process today. Unattended recurring
  monitoring is optional and needs external scheduling; see
  [§8](#8-background-jobs-and-monitoring).
- **Notifications**: console and file channels work with no configuration;
  email (SMTP) and webhook channels activate only if their environment
  variables are set (`.env.example`).
- **Health endpoint**: `GET /api/v1/health` — JSON, aggregates database,
  connector, provider, notification-channel, and monitoring health (see
  `src/web/health.py`).
- **Persistent state**: `data/` (the database file, `.web_secret_key`,
  collected images/raw pages/cache) and `output/` (generated HTML/JSON
  reports). Both must survive restarts and redeploys — anything else in the
  repository is stateless application code.

## 2. Existing Deployment Support Found

Before this change, none existed: no `Dockerfile`, `docker-compose.yml`,
`Procfile`, `render.yaml`, `fly.toml`, Railway config, CI/CD workflow, or
WSGI/ASGI entry point. `requirements.txt` had no production server (only
Flask's own development server, which Flask's documentation explicitly warns
against using in production). `.env.example` already existed and already
documented every environment variable the application reads.

This change adds: `Dockerfile`, `.dockerignore`, `src/web/wsgi.py` (the WSGI
entry point), `scripts/docker_entrypoint.sh`, `render.yaml`, this guide, a
`waitress` dependency, and a small number of environment-variable-gated
production-safety options in `src/web/configuration.py` /
`src/web/application.py` / `src/core/config.py` — all default to the exact
behavior the app already had, so nothing changes for local development.

## 3. Hosting Recommendation

**Recommended: [Render](https://render.com), Web Service (Docker runtime) +
1 GB persistent Disk.** `render.yaml` in the repository root is a ready-to-use
Blueprint for it.

Why Render fits this specific architecture:

| Requirement | Render |
|---|---|
| Python web service | Yes — runs the repo's own `Dockerfile` directly |
| Persistent storage | Yes — a Disk mounted at `/data`, survives restarts/redeploys (**not available on Render's free plan** — see below) |
| HTTPS | Yes — automatic, terminated at Render's edge |
| Environment variables | Yes — dashboard UI, `sync: false` secrets never touch the repo |
| Health checks | Yes — `healthCheckPath: /api/v1/health` in `render.yaml` |
| Logs | Yes — built-in log viewer, no extra setup |
| Background workers | Partial — see [§8](#8-background-jobs-and-monitoring); this is the one place Render doesn't map cleanly onto this architecture |

**Alternatives considered:**

- **Fly.io** — a genuinely strong fit (Fly Volumes give a persistent disk,
  and Fly Machines support a scheduled-run mode that *can* share the same
  volume as the always-on web machine, which would solve the monitoring-cron
  gap Render has). Not the primary recommendation only because it requires
  the `flyctl` CLI and a `fly.toml` written against a specific account/app
  name to be genuinely useful, whereas Render's dashboard-driven Blueprint
  flow needs nothing account-specific committed to the repo. Worth
  revisiting if unattended recurring monitoring becomes a hard requirement.
- **Railway** — similar shape to Render (Docker web service, persistent
  volumes, env vars, HTTPS, logs); no meaningfully different fit for this
  app, and its pricing/plan structure changes more often than Render's or
  Fly's, so it wasn't chosen as the documented default.
- **A bare VM (e.g. a $5-6/mo Linux box)** — would solve the monitoring-cron
  gap trivially (real `cron(1)`, one filesystem, no disk-sharing
  restriction) and is a reasonable choice if that turns out to matter more
  than managed-platform convenience. Deliberately not chosen as the default
  recommendation because it pushes OS patching, TLS renewal, and process
  supervision back onto whoever operates it — exactly what Render/Fly
  otherwise handle.
- **Heroku** — architecturally fine (Procfile-style Docker deploy, add-on
  disk via a paid dyno + external volume service), but has no free tier at
  all anymore and no cost advantage over Render for this workload, so it
  wasn't chosen either.

None of these were selected by guessing — Render was chosen because it is
the simplest of the group that still satisfies every requirement in
[§1](#1-detected-architecture) except the one (shared-volume cron) that
*no* fully-managed multi-service PaaS satisfies without a workaround; that
tradeoff is the same on Railway and Heroku too, and is documented honestly
in [§8](#8-background-jobs-and-monitoring) rather than hidden.

## 4. Migrations

No separate migration command exists or is needed — `Database()`
(constructed once at process startup by `create_app()`) applies `schema.sql`
plus every unapplied file under `src/storage/migrations/` automatically,
each in its own transaction, before the app starts serving requests. The
Docker entrypoint (`scripts/docker_entrypoint.sh`) runs this explicitly
before starting the server anyway, so a first-time deploy against an empty
`/data` volume initializes its own database with no manual step:

```bash
python -c "from src.storage.database import Database; Database()"
```

A migration that fails raises and aborts startup rather than leaving the
database half-migrated — see `src/storage/database.py`'s own docstring.

## 5. Production Startup Command

```bash
python -m src.web.wsgi
```

Serves the app with [waitress](https://docs.pylonsproject.org/projects/waitress/)
(pure-Python, cross-platform — the same command works identically on
Windows, for the local smoke test in [§10](#10-local-production-mode-smoke-test),
and on the Linux container in production) bound to whatever
`WebConfiguration.from_env()` resolves (`WEB_HOST`/`WEB_PORT`, or the
platform-injected `PORT`). This is exactly what `scripts/docker_entrypoint.sh`
runs after migrations and the health check succeed, and exactly what the
`Dockerfile`'s `ENTRYPOINT` invokes.

Never use `flask run` (the development server) or `debug=True` in
production — `WEB_DEBUG` already defaults to `0`/off, and nothing in this
change alters that default.

## 6. Required Environment Variables

Full reference (with defaults and explanations): `.env.example`. Summary of
what actually matters for a production deploy:

| Variable | Required? | Purpose |
|---|---|---|
| `WEB_SECRET_KEY` | **Yes, in production** | Session/CSRF signing key. `scripts/docker_entrypoint.sh` refuses to start without it — see [§9](#9-production-safety-checklist). |
| `RENTAL_AGENT_DATA_DIR` | Yes, if using a mounted volume | Redirects the database + collected files to persistent storage (default in the Docker image: `/data`). |
| `RENTAL_AGENT_OUTPUT_DIR` | Yes, if using a mounted volume | Redirects generated reports to persistent storage (default: `/data/output`). |
| `WEB_ALLOW_NETWORK` | Yes | Must be `1` for the app to bind beyond localhost — the app's own explicit opt-in to being reachable at all. |
| `WEB_SECURE_COOKIES` | Recommended | Sets the `Secure` cookie flag. Only correct once HTTPS actually reaches the app (true on Render/Fly/Railway's managed edges). |
| `WEB_TRUST_PROXY` | Recommended | Trusts one hop of `X-Forwarded-*` headers from the platform's reverse proxy. |
| `RENTCAST_API_KEY` | No | Enables the real RentCast data connector; demo connectors work with no key. |
| `SMTP_*` / `WEBHOOK_*` | No | Enable email/webhook notification channels; console/file channels need nothing. See [§14](#14-notification-delivery-verification). |
| `WEB_ENABLE_SCHEDULER` / `WEB_SCHEDULER_INTERVAL_SECONDS` | No | Runs unattended monitoring inside the web process on a fixed interval. See [§8](#8-background-jobs-and-monitoring). |
| `OPENAI_API_KEY` / `OLLAMA_*` | No | AI provider selection; a null fallback provider works with neither set. |

## 7. Database and Persistent Storage Requirements

One mounted volume, containing:

- `data/rental_intelligence.db` — the SQLite database (must persist)
- `data/.web_secret_key` — the auto-generated fallback secret key (persist,
  or better, set `WEB_SECRET_KEY` explicitly so this file's persistence
  doesn't matter)
- `data/media/`, `data/raw_pages/`, `data/cache/` — collected images/pages/cache
- `output/` — generated reports

1 GB is generous headroom for a pilot-scale deployment; SQLite plus a modest
number of collected listings and reports is small. Nothing here requires a
separate managed database service.

## 8. Background Jobs and Monitoring

On-demand jobs (running a search, running one saved search's monitoring
check "now") need nothing beyond the web service itself — they run in a
background thread inside the same request-serving process and share its
database connection to the same on-disk file, so nothing extra is required
for these to work in production.

**Unattended recurring monitoring detection is resolved (v2.7 Milestone
2.7.3) — unattended notification *delivery* remains a separate, still-manual
step; see the honest distinction below.**

`src/ui/monitoring_cli.py run-due` was originally designed to be invoked
periodically by an OS-level scheduler (cron / Windows Task Scheduler — see
`src/monitoring/scheduling.py::task_scheduler_command_examples()`), reading
and writing the *same* database file the web service uses. On Render (and
Railway, and Heroku), a Cron Job is a **separate service** and cannot mount
the same persistent Disk as the web service — so it cannot see the same
database. This remains true and is a genuine platform limitation, not an
oversight in this repository — but it no longer blocks unattended monitoring
*detection*, because that no longer needs a second service at all:

1. **Recommended: enable the in-process scheduler.** Set
   `WEB_ENABLE_SCHEDULER=1` (optionally `WEB_SCHEDULER_INTERVAL_SECONDS`,
   default `60`) on the web service itself. A background daemon thread
   inside the *same* process calls `MonitoringEngine.run_due()` on that
   interval — same process, same `/data` disk, no second Render service, no
   Redis/Celery/external cron. See `src/web/scheduler.py`. Off by default;
   this is the one explicit opt-in required.
2. **Do nothing extra.** The dashboard's "Run Now" already works fully in
   production without the scheduler enabled; recurring detection is a
   convenience layered on top, not a requirement for the platform to
   function.
3. **Move to Fly.io or a single VM** (unchanged from before) — only
   relevant now if a *separate* worker process is wanted for some other
   reason; the in-process scheduler already removes the disk-sharing
   limitation that used to be the reason to consider this.

**What the scheduler does *not* do: delivery.** `MonitoringEngine` has no
coupling to notifications (verified directly — v2.7 Milestone 2.7.4). It
writes `MonitoringEvent` rows; turning an eligible event into an actual sent
email/webhook is `NotificationEngine.process_pending_deliveries()`/
`process_due_digests()`, triggered today only by a person clicking "Send
now"/"Generate digest" in the dashboard or running `notification-cli`
manually — the scheduler does not call either automatically. This is not a
regression introduced by 2.7.3; docs/31_Notification_Delivery.md's own
design has always kept detection and delivery as separate concerns, and
`notes/Questions.md` already logs "what should drive notification delivery
once this runs somewhere other than a manually-triggered CLI" as an open,
unresolved decision. If unattended delivery is wanted, the same
`WEB_ENABLE_SCHEDULER` thread is the natural place to add it — a genuine
future milestone, not silently assumed here.

## 9. Production Safety Checklist

| Item | Status |
|---|---|
| Production server used instead of the dev server | Done — `waitress` via `src/web/wsgi.py` / `scripts/docker_entrypoint.sh` |
| Debug mode disabled | Already true by default (`WEB_DEBUG` defaults off); unchanged |
| Secret key from environment | Already supported (`WEB_SECRET_KEY`); now **enforced** at container startup (`scripts/docker_entrypoint.sh` exits non-zero if unset) |
| No secrets committed | Verified — `.env` is gitignored and untracked; `.env.example`/`render.yaml` contain only placeholders/`sync: false` |
| Secure cookies available | Added — `WEB_SECURE_COOKIES=1` sets `SESSION_COOKIE_SECURE`; default `0` preserves local HTTP dev |
| Trusted proxy handling | Added — `WEB_TRUST_PROXY=1` applies Werkzeug's `ProxyFix` for one reverse-proxy hop; default `0` preserves local behavior |
| Persistent storage documented | [§7](#7-database-and-persistent-storage-requirements); paths now configurable via `RENTAL_AGENT_DATA_DIR`/`RENTAL_AGENT_OUTPUT_DIR` |
| Migrations run safely in production | [§4](#4-migrations) — automatic, transactional, abort-on-failure; unchanged, already safe |
| Backups and rollback documented | [§11](#11-backup-and-rollback) |
| Logging does not expose secrets | Verified — structured JSON logs (`src/core/agent.py` etc.) log search/run metadata, never SMTP passwords, webhook signing secrets, or the web secret key |
| Health checks work | Verified live — [§10](#10-local-production-mode-smoke-test) |
| Startup/shutdown behavior documented | [§5](#5-production-startup-command); shutdown is a plain SIGTERM to waitress, no special handling needed (no in-flight state beyond the SQLite file, which SQLite itself keeps consistent) |
| Localhost development behavior preserved | Verified — every new setting defaults to today's behavior; full test suite (unchanged) still passes, see [§12](#12-verification) |

## 10. Local Production-Mode Smoke Test

Run with temporary, non-secret placeholder values (no real credentials) —
this is what was actually executed to verify this guide:

```bash
WEB_SECRET_KEY=local-smoke-test-placeholder-key `
WEB_ALLOW_NETWORK=0 `
WEB_PORT=5051 `
RENTAL_AGENT_DATA_DIR=<temp dir>/data `
RENTAL_AGENT_OUTPUT_DIR=<temp dir>/output `
python -m src.web.wsgi
```

Then, against `http://127.0.0.1:5051/`:

1. `GET /api/v1/health` returns `200` with a JSON body reporting database,
   connector, and provider health.
2. `GET /` (the dashboard) returns `200` and renders without a stack trace.
3. Static assets (`/static/...`) return `200`.
4. The response carries the security headers `WebSecurity.apply_security_headers`
   sets (`X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, etc.).
5. No stack trace, secret value, or local filesystem path appears in any
   response body (debug mode is off).

Results of this exact run are recorded in the commit this guide ships with.

## 11. Backup and Rollback

**Application data backup/restore** — unchanged from Version 2.5, already
covered in full in
[35_Installation_and_Operations.md](35_Installation_and_Operations.md)
("Backup" / "Restore"). In production, run `python scripts/backup.py` on a
schedule of your choosing against the same volume the web service uses
(e.g. `docker exec` into the running container, or an equivalent Render
"Shell" session), and copy the resulting `backups/backup_<timestamp>/`
somewhere outside the volume — a Disk snapshot is not a substitute for this,
since it captures the raw filesystem, not a verified-consistent backup.

**Deployment rollback** (code, not data) — with Render/Fly/Railway's
Docker-image-based deploys, rolling back means redeploying the previous
successful image/commit:

```bash
# Render: use the dashboard's "Rollback to this deploy" on any previous
# successful deploy in the service's Events list — no CLI step required.

# Generic (any Docker host): redeploy the previous git commit/tag, e.g.
git checkout v2.6.0 -- .   # or whatever the last-known-good tag is
# then redeploy through the normal deploy path.
```

Because migrations only ever add, never destructively rewrite, existing
data (see `src/storage/migrations/`), rolling back the application code
while leaving a newer database schema in place is safe — older code simply
doesn't read the newer columns/tables.

## 12. Verification

Full test suite and health check, run as part of preparing this guide:

```bash
python -m unittest discover -s tests -t .
python scripts/health_check.py
```

Both must pass before any change in this commit is considered
deployment-ready — see the commit this file ships with for the actual
recorded results.

## 13. Deployment Checklist

Before actually deploying (a separate, explicit step — not performed by
this change):

- [ ] Render account created, GitHub repo connected
- [ ] `render.yaml` Blueprint applied, `starter` plan (or higher) selected
      for persistent Disk support
- [ ] `WEB_SECRET_KEY` generated (`python -c "import secrets; print(secrets.token_hex(32))"`)
      and set in the Render dashboard
- [ ] Any optional provider keys (`RENTCAST_API_KEY`, `SMTP_*`, `WEBHOOK_*`)
      set if those features are wanted
- [ ] First deploy triggered, `/api/v1/health` checked against the live URL
- [ ] A real backup taken (`scripts/backup.py`) and verified
      (`scripts/verify_backup.py`) against the live volume at least once

## 14. Notification Delivery Verification

v2.7 Milestone 2.7.4 — verification and documentation only; see
`docs/46_Version_2.7_Planning.md` Milestone 2.7.4 and Finding 7. Email and
webhook channels (`src/notifications/channels/`) were already fully built
in v2.5 Step 15 — nothing in this section is new code. For the full
technical model (message/template/retry/rate-limit/quiet-hours behavior),
see `docs/31_Notification_Delivery.md`; this section covers only what's
specific to *this production deployment*.

### Verified findings

- **Configuration**: both channels read a config-dict key first, then fall
  back to the matching environment variable (`smtp_host`/`SMTP_HOST`,
  `url`/`WEBHOOK_URL`, etc. — full list in `docs/31_Notification_Delivery.md`
  "Email Configuration"/"Webhook Configuration"). `is_enabled()` is always a
  live `validate_configuration()` check, never a cached flag — a channel
  genuinely cannot claim to be enabled while misconfigured.
- **Credential loading**: read directly from `os.environ` at send time (or
  an explicit per-instance config dict, used only by tests) — never written
  to disk, never logged, never included in `channel_info()`/
  `serialize_result()`/`preview()`.
- **Failure handling**: every documented SMTP/HTTP failure mode (auth
  failure, connection error, server error, timeout, HTTP 4xx/5xx) is caught
  inside the channel's own `send()` and converted into a structured
  `NotificationChannelResult(success=False, error_category=...)` —
  `NotificationChannel.send()`'s own contract is "never raises for an
  ordinary delivery failure." Verified directly against both channels'
  existing test suites (`tests/notifications/test_email_channel.py`,
  `test_webhook_channel.py`) — every failure branch is exercised through a
  fake/mock transport, no real socket ever opens.
- **Secret redaction**: both channels' `_redact()` strips a configured
  password/signing secret out of any exception text before it becomes
  `result.error` — verified by
  `test_authentication_failure_is_categorized_and_password_is_redacted`
  (email) and `test_transport_error_is_categorized_as_connection_error_and_redacted`
  (webhook), plus `test_preview_never_sends_and_never_leaks_password`/
  `test_serialize_result_never_echoes_configuration`. No log line in either
  channel or in `NotificationEngine._attempt_delivery()` ever includes raw
  config — only `channel`, `success`, `error` (already redacted),
  `error_category`, `duration_ms`.
- **Monitoring/scheduler integration**: `MonitoringEngine` (including the
  in-process scheduler added in [§8](#8-background-jobs-and-monitoring))
  has zero coupling to notifications — confirmed by direct inspection, zero
  matches for "notification" anywhere in `src/monitoring/engine.py`. A
  notification failure therefore cannot reach scheduled monitoring at all
  today, because nothing in the scheduled path calls into notifications.
  Delivery itself (when manually triggered from the dashboard) runs inside
  a normal Flask request; an unhandled exception there is caught by
  `WebErrorHandler`'s registered `500` handler (`src/web/error_handler.py`)
  the same as any other route — never a process crash, never a raw
  traceback shown to the user.
- **No live send required for tests**: confirmed no `smtplib.SMTP`/
  `urllib.request.urlopen` (or equivalent) call exists anywhere in
  `tests/notifications/` — every test drives a fake `EmailTransport`/mock
  `HttpTransport` instead.

### Production configuration — SMTP email

Set in the Render dashboard's environment variables (never committed —
`render.yaml` already marks these `sync: false`):

| Variable | Required | Notes |
|---|---|---|
| `SMTP_HOST` | Yes | Your provider's SMTP hostname. |
| `SMTP_PORT` | No (default `587`) | `465` if using `SMTP_USE_SSL=1` instead of STARTTLS. |
| `SMTP_USERNAME` | Usually | Most providers require auth even for STARTTLS. |
| `SMTP_PASSWORD` | Usually | An app-specific password if your provider supports one — never your account's main password. |
| `SMTP_SENDER` | Yes | The `From:` address; the channel is disabled without it. |
| `SMTP_RECIPIENT` | Yes, unless every notification preference sets its own | Default recipient when a message carries no per-send override. |
| `SMTP_USE_TLS` / `SMTP_USE_SSL` | No (defaults `true`/`false`) | Exactly one should be `true` for most providers. |

### Production configuration — webhook

| Variable | Required | Notes |
|---|---|---|
| `WEBHOOK_URL` | Yes | Must be `http://` or `https://`; the channel is disabled otherwise. |
| `WEBHOOK_SIGNING_SECRET` | Recommended | Enables an `X-Signature-256: sha256=<hmac>` header so the receiving endpoint can verify authenticity. |

### Production configuration — enabling the scheduler

Covered fully in [§8](#8-background-jobs-and-monitoring); the two relevant
variables are `WEB_ENABLE_SCHEDULER=1` and, optionally,
`WEB_SCHEDULER_INTERVAL_SECONDS`. Enabling it makes monitoring detection
unattended; it does **not** by itself make notification delivery
unattended (see [§8](#8-background-jobs-and-monitoring)'s "What the
scheduler does *not* do").

### Testing both channels safely, without exposing credentials

- **Automated tests (this repo's own suite)**: already safe by
  construction — `tests/notifications/test_email_channel.py`/
  `test_webhook_channel.py` never touch a real socket. Run them directly
  any time: `python -m unittest discover -s tests/notifications -t .`
- **Local manual verification, no real send**: `notification-cli
  preview-notification --preference-id <id> --event-ids <id> --channel
  email` (or `--channel webhook`) renders exactly what would be sent
  (subject/body, or the JSON payload for webhook) without calling `send()`
  at all — safe with real-looking config, since `preview()` is
  contractually forbidden from performing the network side effect.
  `notification-cli send-test-notification --preference-id <id> --channel
  email` sends exactly one real message through the configured channel —
  the deliberate, explicit way to test a real send once, rather than
  waiting for a genuine monitoring event.
- **First real send, once in production**: use a destination you control
  and can safely discard — for email, an inbox you own that you don't mind
  receiving a test alert; for webhook, a temporary webhook-capture/
  inspection URL (several free tools exist for exactly this purpose — pick
  one you trust, this guide does not endorse a specific one) so you can
  see the exact payload without standing up your own receiver first. Set
  the real env vars in the Render dashboard, run `send-test-notification`
  (or trigger the dashboard's "Send now" against a real pending event),
  confirm it arrives, then
  either leave the config as-is (if it's your real destination) or replace
  it with your real one.
- **Never**: put a real SMTP password or webhook signing secret in a
  commit, a test file, this documentation, or a chat/log message. `.env`
  is gitignored; `.env.example`/`render.yaml` only ever contain empty
  placeholders or `sync: false`.

### Expected behavior when credentials are missing or invalid

- **Missing** (e.g. `SMTP_HOST` or `WEBHOOK_URL` unset): the channel
  reports `is_enabled() == False`; `NotificationEngine` simply excludes it
  from a preference's eligible channels — no error, no crash, the other
  configured channels (console/file, always enabled) continue to work.
- **Present but wrong** (bad password, unreachable host, invalid/denied
  webhook URL): `send()` returns `success=False` with a specific
  `error_category` (`unauthorized`, `connection_error`, `server_error`,
  `invalid_configuration`, or `rejected`), recorded as a
  `channel_health_observations` row and a `NotificationAttempt`. A
  retryable category (`connection_error`/`server_error`) is retried later
  per `NotificationPolicy`'s backoff, up to `dead_letter_after_attempts`;
  `unauthorized`/`invalid_configuration`/`rejected` are not retried, since
  no amount of waiting fixes a bad password or a malformed URL.

### Troubleshooting common notification failures

See `docs/31_Notification_Delivery.md` "Troubleshooting" for the general
cases (a channel showing "not currently configured," a digest never
generating, a delivery stuck `RETRY_SCHEDULED`, missing original listing
URLs). Deployment-specific additions:

- **A channel that works locally shows `unauthorized`/`connection_error`
  only on Render.** Almost always an env var typo or a provider that
  blocks the outbound port Render uses — verify the exact variable names
  above are set (not just present locally in `.env`) via the Render
  dashboard, and check the provider's own outbound-port requirements.
- **Nothing is ever delivered even though a channel is enabled.** Check
  whether anything is actually calling `process_pending_deliveries()`/
  `process_due_digests()` — per this section's own finding, the scheduler
  does not do this automatically; confirm a person is using "Send now" or
  a `notification-cli` invocation, or that a genuinely automated trigger
  has been added deliberately (a future milestone, not assumed here).
- **A webhook signature verification fails on the receiving end.** Confirm
  `WEBHOOK_SIGNING_SECRET` is identical on both sides and that the
  receiver is hashing the exact raw request body (not a re-serialized
  copy) — `X-Signature-256` is computed over the literal `payload_json`
  bytes sent.

## Related Documents

- [31_Notification_Delivery.md](31_Notification_Delivery.md) — full technical model behind [§14](#14-notification-delivery-verification)
- [32_Web_Dashboard.md](32_Web_Dashboard.md)
- [35_Installation_and_Operations.md](35_Installation_and_Operations.md)
- [34_Security_Acceptance.md](34_Security_Acceptance.md)
- [46_Version_2.7_Planning.md](46_Version_2.7_Planning.md) — Milestone 2.7.4
