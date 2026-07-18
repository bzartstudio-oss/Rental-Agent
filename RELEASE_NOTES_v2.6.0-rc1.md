# Release Notes — Version 2.6.0-rc1

The first Release Candidate of Version 2.6 of the Autonomous Rental
Intelligence Platform. Implements the approved roadmap in
`docs/41_Version_2.6_Planning.md`, built on top of `v2.5.0-rc2` (commit
`51c5d4b`, already promoted through `platform-v1` to `main`). **Both v2.5
tags (`v2.5.0-rc1`, `v2.5.0-rc2`) remain unchanged and immutable** — nothing
about them was moved, deleted, or rewritten.

## Why Version 2.6 Exists

The v2.5 pilot session
(`docs/38_Pilot_Feedback_pilot-valencia-01_2026-07-17.md`) found one
release-blocking defect (fixed in RC2 — broken apartment images) and six
non-blocking findings, all purely about the demo/pilot experience, not the
underlying engines. Version 2.6 closes essentially every one of those six
findings, plus the "no config-file loader" gap the pilot session's own
manual-transcription workflow made obvious, through five small, focused
milestones — not a new feature sprint.

## What Changed Since v2.5.0-rc2

### Milestone 2.6.1 — Pilot Materials Correctness
`config/pilot.example.json`'s example budget (350-750 EUR) matched none of
the demo connector fixture prices (950-2600 EUR); its `currency`/proximity
values unconditionally zeroed every demo result. Corrected. The apartment
detail page's geographic-analysis section rendered a raw Python dict repr
instead of a clean "not available" message when no geo data existed. Fixed.

### Milestone 2.6.2 — Demo Fixture Realism
Demo connector fixtures (`demo_platform`/`demo_platform_two`) never
populated `currency`, `property_type`, or coordinates — the only
credential-free connectors could never demonstrate the `currency`/
`property_type` filters or real geographic analysis. Both fixtures now
carry real values for all 6 listings (EUR currency; a mix of apartment/
studio/house property types; real Valencia-area coordinates).

### Milestone 2.6.5 — Saved-Search Name Validation
Duplicate saved-search names were allowed with no warning (the pilot
session created two both named `pilot-valencia-01`). A uniqueness check now
rejects a duplicate name at creation time — enforced only going forward,
never retroactively: saved searches that already share a name (like the two
from the pilot session) still read and run fine.

### Milestone 2.6.4 — Monitoring Test Fixture Variation
Real monitoring runs against demo connectors could never produce a genuine
price/availability/new-match change event, at any number of repeated runs,
because the demo fixtures were 100% static. A second, deterministic "week
2" fixture snapshot (one real price drop, one real availability change, one
real new listing, one deliberately-unchanged control listing) plus a
test-only fixture-swap mechanism now makes this genuinely demonstrable
end-to-end, without any change to `MonitoringEngine` itself.

### Milestone 2.6.3 — Configuration Loading
`config/pilot.example.json` was "a reference document, not an importable
file" (its own prior `_meta.how_to_use`) — nothing in the platform could
load it. The New Search dashboard form now has an optional "Load from a
config file" upload that reads a JSON file matching that same shape and
reuses every existing form-validation rule unchanged. One real defect was
found and fixed during this work: `property_and_room.number_of_rooms`/
`.room_type` look like they should map onto the registered
`number_of_rooms` filter, but that filter is an *exact total-bedroom-count
match* — a different question from "how many rooms does the pilot user
need in a shared flat." Auto-mapping them silently zeroed every demo
result; both fields are deliberately left unmapped instead, with a
regression test locking in the fix.

### Not Changed
Everything else from v2.5.0-rc2 is unchanged — same architecture, same
engines, same security posture. No new product features, no redesign, no
migrations.

## Categorized Feature Status

Unchanged from v2.5.0-rc2 except where noted:

### Fully Implemented and Live-Tested
- Search pipeline (discovery → connectors → analysis → filtering →
  geographic enrichment → ranking → reporting)
- Dynamic Filter Engine (39 filters, composable AND/OR/NOT) — **`currency`
  and `property_type` now genuinely discriminate against demo-connector
  results (2.6.2)**
- Geographic Intelligence Engine — **demo apartments now carry real
  coordinates (2.6.2); the detail page's "not available" state is now a
  clean message, not a raw dict repr (2.6.1)**
- Intelligent Ranking Engine V2 (explainable, evidence-based, user-weighted)
- User Feedback and Preference Learning (explicit/suggested/assisted modes,
  full undo/reset/explain)
- Continuous Monitoring & Saved Searches — **change-detection is now
  genuinely demonstrable against demo connectors via the week-2 fixture
  snapshot (2.6.4); saved-search names are now validated for uniqueness at
  creation (2.6.5)**
- Notification Delivery (console/file channels; email/webhook once
  configured)
- Automatic Platform Discovery (deterministic-fixture-tested)
- Web Dashboard + JSON API — **New Search now accepts an optional
  config-file upload (2.6.3)**
- Backup, restore, and installation health check tooling

### Fixture-Tested (Deterministic, No Live Network)
Unchanged from v2.5.0-rc2 — every connector test, discovery test, and
acceptance journey runs against local Playwright-rendered fixtures or a
fake `PageFetcher`/mock HTTP transport, never a real commercial site.

### Provider-Dependent
Unchanged from v2.5.0-rc2: RentCast (`RENTCAST_API_KEY`), Email/Webhook
notification channels (real credentials), Ollama AI provider (local
server).

### Blocked by External Access Restrictions
Unchanged: no commercial rental platform connector exists in this release.

### Experimentally Implemented / Known Gaps
- **Proximity filters still need a curated reference point.** Populating
  apartment coordinates (2.6.2) was necessary but not sufficient — the
  `walking_distance`/`public_transport_time` analyzers also need a curated
  `city_center`/`public_transport` `knowledge_entries` reference point for
  the *exact* search location, and nothing seeds that automatically. Set
  one manually (see `docs/37_Pilot_Operations_Guide.md` section 9) to see
  these filters genuinely discriminate.
- A filter-value validation error surfaces as a job's `error_summary`
  string, not an immediate form-level 400 (unchanged from v2.5).
- **A pre-2.6.2 local database does not retroactively backfill
  currency/property_type/coordinates.** `apartment_repository`'s
  re-observation update path deliberately only refreshes price/status/
  title/description — a Migration-0004-era design choice, not a Version 2.6
  regression. Fresh databases (every automated test, and any new
  installation) are unaffected.
- **The saved-search "Run now" job-status page 404s on its own
  client-side auto-redirect after a monitoring run completes**, even
  though the run itself completes correctly (visible on the saved-search
  detail page and via the JSON API). Pre-existing Version 2.5 Step 16
  behavior, out of this release's scope.

### Deferred (Not Built This Release, By Design)
Unchanged from v2.5.0-rc2: mobile applications, multi-tenant billing,
autonomous connector generation, a real task queue, full multi-user
authentication, an OS-level scheduler inside the web server, PDF reports.

## Upgrade Instructions

From v2.5.0-rc2 (or `main`/`platform-v1`, which are at the same commit):

```bash
git fetch
git checkout feature/v2.6
git pull
pip install -r requirements.txt   # unchanged from v2.5
python -m playwright install chromium
python scripts/backup.py --label pre-upgrade   # recommended before any upgrade
python -c "from src.storage.database import Database; Database()"  # applies any new migrations (none new in v2.6.0-rc1)
python scripts/health_check.py
```

No new migrations in Version 2.6 (still 11, unchanged from v2.5). No manual
data migration is required. If you want the new fixture/filter fields
(currency, property_type, coordinates) to appear on apartments your
database already observed before upgrading, see the known-gap note above —
they only populate on a fresh observation, not retroactively.

## Rollback Instructions

```bash
git checkout <previous-commit-or-tag>   # e.g. v2.5.0-rc2 (51c5d4b), still valid and unchanged
pip install -r requirements.txt
python scripts/restore.py <pre-upgrade-backup> --to <project-root> --force
```

## Acceptance Summary

- **1344 tests passing, 0 failures, 0 skipped.**
- **Full integration acceptance**: `docs/42_Version_2.6_Acceptance_Report.md`
  — full suite, health check, fresh-database migration verification,
  backup/restore, CLI startup, a live 16-step end-to-end dashboard
  workflow, config-loader regression proof, and full security verification.
  Decision: **PASS**.
- **Security acceptance**: unchanged security posture from v2.5, plus the
  new config-file upload path independently verified in this release's own
  acceptance report (malformed/invalid input rejected the same way form
  submission already is; no new trust boundary).
- **Backup/restore**: unchanged from v2.5, still verified passing (10/10),
  plus a live standalone round-trip demonstration.
- **Clean-install verification**: `scripts/health_check.py` — 13/13 checks
  PASS.

## Known Limitations

See MASTER_SPEC.md Section 44, `docs/33_Release_Candidate_Acceptance.md`'s
"Known Gaps," `docs/41_Version_2.6_Planning.md`'s Section 5 ("Features
Explicitly Out of Scope"), and `docs/42_Version_2.6_Acceptance_Report.md`'s
"Known Limitations" for the complete, current list.

## Open Issues

See `notes/Questions.md` for the live, current queue of unresolved
decisions, each tagged with which document it blocks.
