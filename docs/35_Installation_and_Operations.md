# 35 — Installation and Operations

Version 2.5 Step 17. Everything a new developer or local user needs to
install, start, test, back up, restore, and health-check this platform,
without relying on any prior conversation or tribal knowledge.

## Requirements

- Python 3.11+ (developed and tested on 3.13)
- A modern OS (developed and tested on Windows 11; PowerShell examples below,
  but every command is also plain `python -m ...` and works identically on
  macOS/Linux)
- ~200 MB free disk for Playwright's bundled Chromium

## Installation

```bash
python -m venv .venv

# Windows
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium

# macOS/Linux
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium

cp .env.example .env   # then fill in whichever optional values you want
```

## Health Check

Run this after installing, and any time something seems off:

```bash
python scripts/health_check.py
# or, for machine-readable output:
python scripts/health_check.py --json
```

Checks: Python version, required dependencies, Playwright's Chromium
install, configuration loading, writable `data/`/`output/` directories,
database accessibility, migration status, web binding (localhost vs.
network-exposed), connector/provider/geographic-provider registries,
notification channel configuration, and free disk space. Every check reports
`PASS`/`WARN`/`FAIL`; the process exits non-zero only on a real `FAIL`.

## Database Initialization / Migrations

There is no separate "init" command — `Database()` (constructed by every
CLI and by `create_app()`) applies `schema.sql` plus every numbered file
under `src/storage/migrations/` automatically, exactly once each, the first
time it's called against a given database file:

```bash
python -c "from src.storage.database import Database; Database()"
```

## Running the Test Suite

```bash
python -m unittest discover -s tests -t .
```

Sub-suites, if you only need one area:

```bash
python -m unittest discover -s tests/web -t .          # web dashboard + API
python -m unittest discover -s tests/acceptance -t .    # Journeys A-F
python -m unittest discover -s tests/scripts -t .       # backup/restore/health-check
```

## Starting the CLI

```bash
python -m src.ui.cli --location "Example City"
```

Every other CLI (`monitoring_cli.py`, `notification_cli.py`,
`feedback_cli.py`, `discovery_cli.py`) is invoked the same way, e.g.:

```bash
python -m src.ui.monitoring_cli --help
```

## Starting the Web Dashboard

```bash
python -m flask --app "src.web.application:create_app" run
```

Windows PowerShell convenience script (runs the health check first, then
starts the server):

```powershell
.\scripts\start_web.ps1
```

Bound to `127.0.0.1:5000` by default. Set `WEB_ALLOW_NETWORK=1` (in `.env`
or the environment) to bind `0.0.0.0` instead — the one explicit opt-in this
platform requires to expose itself on the network.

## Backup

```bash
python scripts/backup.py                      # writes backups/backup_<timestamp>/
python scripts/backup.py --compress            # writes a single .zip instead
python scripts/backup.py --label pre-upgrade   # adds a label to the folder/archive name
```

Includes: the SQLite database (via SQLite's own online backup API — safe
even while the app is running), `data/raw_pages/`, `data/media/`,
`output/` (reports, and any file-channel notification output already under
it), `.env.example` (never `.env` itself), and a `manifest.json` with a
SHA-256 checksum + size per file plus the applied migration versions and
release metadata (git commit hash, `VERSION` contents).

**Never included**: `.env`, `data/.web_secret_key`, or any notification
channel credential (SMTP password, webhook signing secret) — these live only
in environment variables/`.env`, never copied by the backup script.

## Verifying a Backup

```bash
python scripts/verify_backup.py backups/backup_20260101T000000Z
python scripts/verify_backup.py backups/backup_20260101T000000Z.zip --json
```

Re-checks every file's checksum/size against the manifest and runs
`PRAGMA integrity_check` against the backed-up database — without restoring
anything.

## Restore

```bash
# Preview only — lists what would be restored, writes nothing:
python scripts/restore.py backups/backup_20260101T000000Z --to /tmp/restored --preview

# Restore to a fresh (or explicitly --force'd non-empty) location:
python scripts/restore.py backups/backup_20260101T000000Z --to /tmp/restored
python scripts/restore.py backups/backup_20260101T000000Z --to /tmp/restored --force
```

Restoring always requires an explicit `--to DESTINATION` — this script never
implicitly overwrites `data/`/`output/` in place. A backup fails verification
(corrupt checksum, failed database integrity check) before a single file is
written. Restoring into a non-empty destination requires the explicit
`--force` flag. After restore, the destination's database automatically
passes `PRAGMA integrity_check` — restore itself raises if it doesn't.

**Recovery procedure**: stop the app (if running) → `python scripts/backup.py`
(a final safety backup of current state, optional but recommended) →
`python scripts/restore.py <chosen-backup> --to <project-root-or-elsewhere> --force`
→ `python scripts/health_check.py` → restart the app.

## Configuration Reference

See `.env.example` for the full, current list of optional environment
variables (AI provider keys, the RentCast API key, web host/port/binding,
SMTP/webhook notification channel settings) — every one of them is read
directly from the real source files listed there, not invented for this
document.

## Troubleshooting

- **`ModuleNotFoundError` on startup** — dependencies weren't installed into
  the active `.venv`; re-run `pip install -r requirements.txt` with the
  correct interpreter.
- **Playwright errors ("Executable doesn't exist")** — run
  `python -m playwright install chromium`.
- **`sqlite3.OperationalError: unable to open database file`** — the `data/`
  directory doesn't exist or isn't writable; `scripts/health_check.py` will
  catch and report this directly.
- **Web dashboard shows "CSRF token missing"** — the browser session cookie
  was lost (e.g. the server restarted with a different secret key); reload
  the form page and resubmit.
- See docs/32_Web_Dashboard.md's own "Troubleshooting" section for
  web-specific issues.

## Related Documents

- [32_Web_Dashboard.md](32_Web_Dashboard.md)
- [33_Release_Candidate_Acceptance.md](33_Release_Candidate_Acceptance.md)
- [36_Performance_Baseline.md](36_Performance_Baseline.md)
