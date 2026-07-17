# Release Notes — Version 2.5.0-rc1

The first Release Candidate of the Autonomous Rental Intelligence Platform.
This release bundles every sprint from V1.0 through Version 2.5 Step 17
(Release Candidate Acceptance) into one verified, documented, packaged
whole, installable and testable by a new developer without any prior
conversation context.

## What This Release Is

A local, single-user platform (CLI + web dashboard + JSON API) that
searches, ranks, monitors, and explains rental apartment listings, backed
by SQLite, with real backup/restore tooling and an installation health
check.

## Categorized Feature Status

Every feature below is labeled honestly — never overstated.

### Fully Implemented and Live-Tested
- Search pipeline (discovery → connectors → analysis → filtering →
  geographic enrichment → ranking → reporting)
- Dynamic Filter Engine (39 filters, composable AND/OR/NOT)
- Geographic Intelligence Engine (haversine-based distance/travel-time/
  nearby search)
- Intelligent Ranking Engine V2 (explainable, evidence-based, user-weighted)
- User Feedback and Preference Learning (explicit/suggested/assisted modes,
  full undo/reset/explain)
- Continuous Monitoring & Saved Searches (versioned, scheduled or manual)
- Notification Delivery (console/file channels; email/webhook once
  configured)
- Automatic Platform Discovery (deterministic-fixture-tested; see
  "Provider-Dependent" below for real network verification)
- Web Dashboard + JSON API (Flask, server-rendered, CSRF-protected,
  localhost-only by default)
- Backup, restore, and installation health check tooling

### Fixture-Tested (Deterministic, No Live Network)
- Every connector test, every discovery test, and every acceptance journey
  (`tests/acceptance/`) runs against local Playwright-rendered fixtures or a
  fake `PageFetcher`/mock HTTP transport — never a real commercial site.
  This is intentional, per this platform's own testing discipline (docs/33),
  not a shortcut.

### Provider-Dependent
- **RentCast** is the one real, non-demo data connector — requires a
  `RENTCAST_API_KEY` (free tier available) to actually query listings.
  Without one, the platform runs entirely on deterministic demo connectors.
- **Email/Webhook notification channels** require real SMTP credentials or a
  webhook URL — both remain disabled (honestly reported as such) until
  configured.
- **Ollama AI provider** requires a locally running Ollama server; the
  null/no-op AI provider is the default fallback.

### Blocked by External Access Restrictions
- No commercial rental platform (Zillow, Apartments.com, Rightmove,
  Idealista, Fotocasa, ImmoScout24, etc.) has a real connector in this
  release — building one requires an explicitly approved API/feed
  integration per each platform's own Terms of Service, which is outside
  this project's current scope. **This release does not claim any of these
  platforms are supported.**

### Experimentally Implemented / Known Gaps (see docs/33 for full detail)
- `walking_distance`/`public_transport_time` filters are a normalized
  proximity *score* (`0.0`-`1.0`), not literal minutes.
- A filter-value validation error surfaces as a job's `error_summary`
  string, not an immediate form-level 400.
- `property_type` filtering cannot be meaningfully exercised against demo
  connector fixtures (only RentCast populates that field).

### Deferred (Not Built This Release, By Design)
- Mobile applications, multi-tenant billing, autonomous connector
  generation, a real task queue (Celery/Redis), full multi-user
  authentication, an OS-level scheduler inside the web server, PDF reports.

## Upgrade Instructions

From any prior Version 2.5 step:

```bash
git fetch
git checkout release/v2.5-rc1
pip install -r requirements.txt   # Flask (Step 16) added; pandas/numpy/
                                    # reportlab/python-docx removed (unused —
                                    # see CHANGELOG)
python -m playwright install chromium
python scripts/backup.py --label pre-upgrade   # recommended before any upgrade
python -c "from src.storage.database import Database; Database()"  # applies any new migrations
python scripts/health_check.py
```

No manual data migration is required — `Database()` applies every new
migration automatically and idempotently; existing data is never modified
by an upgrade, only added to.

## Rollback Instructions

```bash
git checkout <previous-commit-or-tag>
pip install -r requirements.txt
python scripts/restore.py <pre-upgrade-backup> --to <project-root> --force
```

Migrations in this codebase are additive-only and never delete a column or
table, so a rollback of *code* alone (without restoring the pre-upgrade
backup) is also safe — older code simply won't read the newer tables/columns
it doesn't know about.

## Acceptance Summary

- **1308 tests passing, 0 failures, 0 skipped** (see docs/33 Phase 1/11; also
  independently re-verified in Step 18's own pre-tag check, see
  docs/39_Tag_Readiness_v2.5.0-rc1.md).
- **Full end-to-end acceptance matrix**: docs/33_Release_Candidate_Acceptance.md.
- **Security acceptance**: docs/34_Security_Acceptance.md — all checks PASS.
- **Backup/restore**: verified — creation, checksum verification, corruption
  detection, alternate-location restore, safe overwrite refusal, restored
  startup, and historical-data preservation are all real, passing tests
  (`tests/scripts/test_backup_restore.py`).
- **Clean-install verification**: `scripts/health_check.py` — 13/13 checks
  PASS on a real, freshly-migrated installation.

## Known Limitations

See MASTER_SPEC.md Section 44 and docs/33's "Known Gaps" for the complete,
current list.

## Open Issues

See `notes/Questions.md` for the live, current queue of unresolved
decisions (real task-queue choice, multi-user auth mechanism, additional
notification channels, etc.), each tagged with which document it blocks.
