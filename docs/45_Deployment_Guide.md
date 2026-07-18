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
| `SMTP_*` / `WEBHOOK_*` | No | Enable email/webhook notification channels; console/file channels need nothing. |
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

**Unattended recurring monitoring is the one gap.** `src/ui/monitoring_cli.py
run-due` is designed to be invoked periodically by an OS-level
scheduler (cron / Windows Task Scheduler — see
`src/monitoring/scheduling.py::task_scheduler_command_examples()`), reading
and writing the *same* database file the web service uses. On Render (and
Railway, and Heroku), a Cron Job is a **separate service** and cannot mount
the same persistent Disk as the web service — so it cannot see the same
database. This is a genuine platform limitation, not an oversight in this
repository.

This deployment does not attempt to route around that limitation with a
fragile workaround (e.g. a second in-container cron daemon fighting the web
process for PID 1). If unattended recurring monitoring is required in
production, the options — in order of how well they fit this platform's
architecture — are:

1. **Do nothing extra.** The dashboard's "Run Now" already works fully in
   production; recurring monitoring is a convenience, not a requirement for
   the platform to function.
2. **Move to Fly.io**, whose scheduled Machines can share a Fly Volume with
   the always-on web Machine — the same filesystem, so `run-due` sees the
   same database. Not set up here (see [§3](#3-hosting-recommendation) for
   why it isn't the default recommendation), but is the natural next step
   if this becomes a requirement.
3. **Move to a single VM** with a real crontab entry running `run-due`
   against the same local disk the web process uses.

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

## Related Documents

- [32_Web_Dashboard.md](32_Web_Dashboard.md)
- [35_Installation_and_Operations.md](35_Installation_and_Operations.md)
- [34_Security_Acceptance.md](34_Security_Acceptance.md)
