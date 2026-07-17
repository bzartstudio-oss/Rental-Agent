# 37 — Pilot Operations Guide

Version 2.5 Step 18. A step-by-step guide for a pilot operator running the
Autonomous Rental Intelligence Platform v2.5.0-rc2 (or later) against the documented
Valencia reference scenario, using only commands and behavior that exist and
are tested in this release. Every command below matches
`docs/35_Installation_and_Operations.md` and the actual CLI/script argument
lists in `src/ui/*.py` and `scripts/*.py` — nothing here is aspirational.

## 1. Pilot Objective

Let a real person — not the development team — install the platform, run a
realistic rental search against a real address (Valencia, Spain), review the
results end to end (listings, images, comparison, reports), and record
structured feedback (`docs/38_Pilot_Feedback_Template.md`) on what worked,
what was confusing, and what was wrong. The goal is honest signal on
real-user usability, not a load test or a scraping-coverage test.

## 2. Supported Workflows

- Installing and health-checking the platform
- Running a search via the web dashboard or the CLI against the platform's
  own deterministic demo connectors (`demo_platform`, `demo_platform_two`)
- Reviewing results, images, and per-apartment detail pages
- Comparing multiple apartments side by side
- Recording feedback (save/shortlist/reject/manual rating) and viewing the
  resulting preference profile
- Saving a search and running its monitoring manually (`run-now`)
- Enabling and testing Console/File notification channels
- Backing up and restoring the local database
- Reviewing structured JSON logs

## 3. Unsupported or Provider-Dependent Workflows

- Any real commercial rental platform (Zillow, Idealista, Fotocasa, etc.) —
  no connector exists in this release; do not attempt to point a pilot at one
- RentCast results — only available if the pilot operator independently
  supplies their own `RENTCAST_API_KEY` in a local `.env` file
- Email/webhook notifications — require real SMTP credentials or a webhook
  URL, neither of which this guide or `config/pilot.example.json` provides
- Literal walking/public-transport time limits in minutes — the platform's
  `walking_distance`/`public_transport_time` filters are a normalized
  `0.0`-`1.0` proximity score, not minutes (see Known Limitations, section
  21)
- Loading `config/pilot.example.json` automatically — there is no
  config-file loader in this release; its values are entered manually (see
  section 10)

## 4. Installation

```bash
python -m venv .venv

# Windows
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium

# macOS/Linux
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium

cp .env.example .env
```

No values in `.env` are required for the demo-connector pilot scenario;
leave `RENTCAST_API_KEY`, SMTP, and webhook variables blank.

## 5. Health Check

```bash
python scripts/health_check.py
```

Expect 13/13 `PASS`. A `WARN` on `notification_channels` (email/webhook
"not-yet-configured") is expected and fine for a pilot. Any `FAIL` means stop
and fix before proceeding — see `docs/35_Installation_and_Operations.md`
Troubleshooting.

## 6. Creating a Backup

Before running any pilot search, take a clean baseline backup:

```bash
python scripts/backup.py --label pre-pilot
```

This is the checkpoint section 20 restores to if pilot data needs to be
cleared later.

## 7. Starting the CLI

```bash
python -m src.ui.cli --location "Valencia, Spain" --max-price 750
```

Add `--help` to see every flag. The CLI runs one search and writes an HTML +
JSON report to `output/`.

## 8. Starting the Dashboard

```bash
python -m flask --app "src.web.application:create_app" run
# or, on Windows:
.\scripts\start_web.ps1
```

Open `http://127.0.0.1:5000/` in a browser. Bound to localhost only unless
`WEB_ALLOW_NETWORK=1` is explicitly set.

## 9. Loading the Pilot Configuration

Since v2.6 Milestone 2.6.3 (docs/41_Version_2.6_Planning.md), the dashboard's
New Search form has a "Load from a config file" file upload at the top —
upload `config/pilot.example.json` (or your own copy matching its shape)
directly and most of the fields below fill in automatically. See
`src/web/forms/config_loader.py` for exactly what is and isn't translated.

Automatically loaded from the file: location fields, budget (min/max
price), proximity preferences, amenities, feedback mode, and
`connectors.allowed_platform_ids`.

Still entered by hand, because there is no reliable automatic mapping (see
`config_loader.py`'s own docstring for why each one is skipped rather than
guessed): `destination`, `property_and_room.room_type`/`.number_of_rooms`,
`search.ranking.ranking_profile` (use the Ranking Profile dropdown),
"Enable Monitoring," and any notification preference — leave the last two
unchecked (monitoring/notifications ship disabled by default for pilot
sessions — see sections 15 and the mission's own instruction not to enable
them automatically).

The CLI (`python -m src.ui.cli`) has no config-file loader — its own
`--flags` still need to be entered manually.

## 10. Running the Valencia Search

Destination used throughout this pilot and in `tests/acceptance/`:

```
Carrer Mestre Serrano, 3, 46120 Alboraia, Valencia, Spain
```

Via the dashboard: New Search → enter the location/criteria from section 9 →
Submit → wait for the job to complete → open the results page.

Via the CLI:

```bash
python -m src.ui.cli --location "Valencia, Spain" --max-price 750 --label "pilot-valencia-01"
```

## 11. Reviewing Original Listing URLs

Every apartment detail page and the JSON API (`/api/v1/apartments/<id>`)
include the original connector URL (`original_url`/equivalent field) so a
pilot user can cross-check a result against its source fixture page. Demo
connector results point at local fixture pages, not live commercial sites —
this is expected (see section 3).

## 12. Recording Feedback

Via the dashboard: open an apartment → Save / Shortlist / Reject, or submit
a manual rating.

Via the CLI:

```bash
python -m src.ui.feedback_cli record --profile-id pilot-valencia-01 --event-type save --apartment-id <apartment_id>
python -m src.ui.feedback_cli profile --profile-id pilot-valencia-01 --mode suggested
```

## 13. Saving a Search

Via the dashboard: check "Save this search" on the New Search form (or the
results page), name it, and confirm monitoring stays disabled unless you
intend to test section 14.

Via the CLI:

```bash
python -m src.ui.monitoring_cli create-saved-search --name "pilot-valencia-01" --location "Valencia, Spain" --criteria-json "{}"
```

## 14. Running Monitoring Manually

Monitoring is disabled by default. To deliberately test it during a pilot
session:

```bash
python -m src.ui.monitoring_cli run-now --saved-search-id <saved_search_id>
python -m src.ui.monitoring_cli list-events --saved-search-id <saved_search_id>
```

A saved search's *first* monitoring run cannot itself produce a
`new_match`/`new_listing` event (nothing to compare against yet — see
`docs/33_Release_Candidate_Acceptance.md` Known Gaps #4). Run it a second
time to observe comparison behavior.

## 15. Enabling Console/File Notifications

Console and File channels require no external credentials and are safe for
a pilot session:

```bash
python -m src.ui.notification_cli create-preference --profile-id pilot-valencia-01 --saved-search-id <saved_search_id> --channels console file --immediate-event-types new_match
python -m src.ui.notification_cli deliver-pending
```

Do not create an Email or Webhook preference during a pilot unless you have
independently configured real SMTP/webhook credentials outside this guide.

## 16. Reviewing Logs

This platform emits one structured JSON line per log record to **stderr**
(`src/utils/logging.py`) — there is no persistent log file by default.
Redirect stderr to a file when starting the CLI or dashboard if you need a
persisted log for a pilot session:

```bash
python -m src.ui.cli --location "Valencia, Spain" 2> pilot_session.log
```

## 17. Reporting a Defect

This release has no integrated bug tracker. To report a defect:

1. Fill in a copy of `docs/38_Pilot_Feedback_Template.md` (one per issue or
   per session).
2. Include the exact command or dashboard page, the JSON log lines around
   the failure (section 16), and — for a crash — the full traceback.
3. Share the completed template file directly with the development team
   (e.g., attach it to an email or hand it back with the pilot session's
   `output/` artifacts). Do not paste credentials or `.env` contents into a
   defect report.

## 18. Restoring from Backup

```bash
python scripts/verify_backup.py backups/<backup_name>
python scripts/restore.py backups/<backup_name> --to <destination> --force
python scripts/health_check.py
```

See `docs/35_Installation_and_Operations.md` "Recovery procedure" for the
full sequence, including stopping the app first.

## 19. Stopping the Application

- Dashboard: `Ctrl+C` in the terminal running `flask run` /
  `start_web.ps1`.
- CLI: each invocation runs one search and exits on its own; there is no
  long-running CLI process to stop.
- Monitoring/notification CLIs invoked manually (sections 14-15) also exit
  on their own; nothing runs in the background unless the pilot operator
  separately wired a cron/Task Scheduler entry per
  `docs/30_Continuous_Monitoring.md`/`docs/31_Notification_Delivery.md`
  (not part of this pilot by default).

## 20. Resetting Only Pilot Data Without Deleting Historical Production Data

**Honest limitation**: this release has no selective "delete only this
search's/profile's rows" command. The only supported reset mechanism is a
full point-in-time restore to the checkpoint taken in section 6:

```bash
python scripts/backup.py --label pre-pilot-reset-safety   # optional extra safety backup of current (pilot-included) state
python scripts/restore.py backups/<pre-pilot-backup-from-section-6> --to <project-root> --force
python scripts/health_check.py
```

This restores the database to exactly the state it was in before the pilot
began — it does not selectively remove only pilot rows while preserving
production changes made *during* the pilot window, because no such
selective-delete tool exists yet. If both real production activity and
pilot activity happened in the same window, restoring will discard both.
For that reason, this guide recommends giving all pilot data a distinct,
greppable label/profile-id (e.g., `pilot-valencia-01`, as used throughout
this guide) so it can at least be **identified** even though it cannot yet
be **selectively deleted**. Building a real selective-delete tool is out of
scope for this release (see `notes/Questions.md`).

## 21. Known Limitations

See `docs/33_Release_Candidate_Acceptance.md` "Known Gaps Found During
Acceptance" and `RELEASE_NOTES_v2.5-rc1.md` "Known Limitations" for the
complete, current list. The four most likely to surface during a pilot:

1. `walking_distance`/`public_transport_time` are a `0.0`-`1.0` proximity
   score, not literal minutes.
2. A filter-value validation error surfaces as a job's `error_summary`
   string, not an immediate form-level 400.
3. `property_type` filtering returns zero results against demo connector
   fixtures (only RentCast populates that field).
4. `new_match`/`new_listing` monitoring events require a second observation
   of a saved search.

## 22. Pilot Success Metrics

Recorded per session via `docs/38_Pilot_Feedback_Template.md`:

- Search completed without an unhandled error
- At least one relevant result returned and reviewable end to end (listing →
  detail → original URL)
- Feedback (save/shortlist/reject) recorded and reflected in the preference
  profile
- Report (HTML and/or JSON) generated and opened successfully
- Time from "submit search" to "reviewed first result" (self-reported,
  approximate — no instrumentation is added by this release)
- Overall recommendation (see `docs/38`'s final field)

There is no automated pass/fail threshold across these — the acceptance
criteria for the *platform itself* were already established in
`docs/33_Release_Candidate_Acceptance.md`; this section is about learning
from real usage, not re-running that matrix.

## 23. Rollback Procedure

If the pilot needs to stop and the platform needs to return to its
pre-pilot, tested state entirely (not just the data — the code too):

```bash
git status                              # confirm no uncommitted pilot-only changes you want to keep
git checkout release/v2.5-rc1           # or the specific pre-pilot commit/tag
pip install -r requirements.txt
python scripts/restore.py backups/<pre-pilot-backup-from-section-6> --to <project-root> --force
python scripts/health_check.py
```

This mirrors `RELEASE_NOTES_v2.5-rc1.md`'s own "Rollback Instructions" —
code rollback and data rollback are independent steps; do only the ones
actually needed.

## Related Documents

- [33_Release_Candidate_Acceptance.md](33_Release_Candidate_Acceptance.md)
- [35_Installation_and_Operations.md](35_Installation_and_Operations.md)
- [38_Pilot_Feedback_Template.md](38_Pilot_Feedback_Template.md)
- [39_Tag_Readiness_v2.5.0-rc1.md](39_Tag_Readiness_v2.5.0-rc1.md)
- [40_Tag_Readiness_v2.5.0-rc2.md](40_Tag_Readiness_v2.5.0-rc2.md)
- [38_Pilot_Feedback_pilot-valencia-01_2026-07-17.md](38_Pilot_Feedback_pilot-valencia-01_2026-07-17.md) — a completed example
- [../config/pilot.example.json](../config/pilot.example.json)
