# Release Notes — Version 2.5.0-rc2

The second Release Candidate of the Autonomous Rental Intelligence
Platform — a pilot-driven follow-up to `v2.5.0-rc1`. **`v2.5.0-rc1` remains
unchanged and immutable**: its tag still points at commit `138c8743`, and
nothing about it was rewritten. RC2 adds two new commits on top of it after
a controlled local pilot session surfaced one real, user-visible defect.

## What Changed Since RC1

A controlled local pilot session (`docs/38_Pilot_Feedback_pilot-valencia-01_2026-07-17.md`)
ran the full documented pilot workflow — search, results, apartment detail,
saved search, monitoring, notifications, feedback, discovery, system
health, and the JSON API — against RC1 exactly as shipped. It found one
real, release-worthy defect and six non-blocking, documentation-only
findings.

### Fixed
- **Apartment images never rendered in a real browser** for
  `demo_platform`/`demo_platform_two` results. `ApartmentImage.source_url`
  is a `file://` path for fixture-based connectors — no browser will load
  that from an `http://` page (confirmed via `naturalWidth: 0` in a live
  browser). A same-origin `/apartments/<id>/media/<filename>` route now
  serves the already-downloaded `ApartmentImage.local_path` instead,
  reusing the existing `WebSecurity.safe_join()` path-traversal guard
  rather than inventing new security logic. Reads file bytes eagerly
  (not `send_file`'s streaming wrapper), which was observed leaving a
  file handle open on Windows and blocking temp-directory cleanup in
  tests. 4 new regression tests
  (`tests/web/test_routes.py::ApartmentImageServingTests`).

### Not Changed
Everything else from RC1 is unchanged — same features, same architecture,
same known limitations except where refined below. This release does not
add product features, redesign anything, or fix the six non-blocking
findings (none proved release-blocking).

## Categorized Feature Status

Unchanged from RC1 except where noted:

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
  localhost-only by default) — **now including working apartment images
  for demo-connector results (RC2 fix)**
- Backup, restore, and installation health check tooling

### Fixture-Tested (Deterministic, No Live Network)
- Every connector test, every discovery test, and every acceptance journey
  (`tests/acceptance/`) runs against local Playwright-rendered fixtures or a
  fake `PageFetcher`/mock HTTP transport — never a real commercial site.

### Provider-Dependent
- **RentCast** is the one real, non-demo data connector — requires a
  `RENTCAST_API_KEY` (free tier available) to actually query listings.
- **Email/Webhook notification channels** require real SMTP credentials or a
  webhook URL — both remain disabled (honestly reported as such) until
  configured.
- **Ollama AI provider** requires a locally running Ollama server; the
  null/no-op AI provider is the default fallback.

### Blocked by External Access Restrictions
- No commercial rental platform (Zillow, Apartments.com, Rightmove,
  Idealista, Fotocasa, ImmoScout24, etc.) has a real connector in this
  release. **This release does not claim any of these platforms are
  supported.**

### Experimentally Implemented / Known Gaps (refined from pilot findings — see docs/33 and docs/40 for full detail)
- `walking_distance`/`public_transport_time` filters are a normalized
  proximity *score* (`0.0`-`1.0`), not literal minutes — **and demo
  connector apartments have no coordinates at all, so any threshold value
  excludes every demo-connector result, not merely a semantic mismatch.**
- A filter-value validation error surfaces as a job's `error_summary`
  string, not an immediate form-level 400.
- `property_type` filtering cannot be meaningfully exercised against demo
  connector fixtures (only RentCast populates that field).
- **The `currency` filter always excludes demo-connector apartments** —
  they never populate `Apartment.currency` (same category as the
  `property_type` gap above).
- **Real monitoring runs against demo connectors can never produce a
  genuine price/availability/new-match change event**, at any number of
  repeated runs — demo fixtures are 100% static, so two consecutive runs
  always observe bit-for-bit identical data. This refines the prior
  "requires a second observation" wording, which understated the
  limitation.
- The apartment detail page's geographic-analysis section renders a raw
  Python dict repr instead of a clean "not available" message when no geo
  data exists — cosmetic only.
- Duplicate saved-search names are allowed with no uniqueness warning.
- `config/pilot.example.json`'s example budget (350-750 EUR) returns zero
  results against actual demo connector fixture prices (950-2600 EUR) —
  a documentation accuracy issue, not fixed this release.

### Deferred (Not Built This Release, By Design)
- Mobile applications, multi-tenant billing, autonomous connector
  generation, a real task queue (Celery/Redis), full multi-user
  authentication, an OS-level scheduler inside the web server, PDF reports.

## Upgrade Instructions

From RC1:

```bash
git fetch
git checkout release/v2.5-rc1
git pull
pip install -r requirements.txt   # unchanged from RC1
python -m playwright install chromium
python scripts/backup.py --label pre-upgrade   # recommended before any upgrade
python -c "from src.storage.database import Database; Database()"  # applies any new migrations (none new in RC2)
python scripts/health_check.py
```

No new migrations in RC2 (still 11, same as RC1). No manual data migration
is required.

## Rollback Instructions

```bash
git checkout <previous-commit-or-tag>   # e.g. v2.5.0-rc1 (138c8743), still valid and unchanged
pip install -r requirements.txt
python scripts/restore.py <pre-upgrade-backup> --to <project-root> --force
```

## Acceptance Summary

- **1312 tests passing, 0 failures, 0 skipped** (1308 from RC1 plus 4 new
  image-serving regression tests).
- **Full end-to-end acceptance matrix**: docs/33_Release_Candidate_Acceptance.md
  (unchanged from RC1 — no acceptance criteria were altered).
- **Security acceptance**: docs/34_Security_Acceptance.md — all checks PASS
  (unchanged from RC1; the new media route reuses the existing
  `WebSecurity.safe_join()` path-traversal guard, independently re-verified
  in this release's own tag-readiness check — see docs/40).
- **Backup/restore**: unchanged from RC1, still verified passing.
- **Clean-install verification**: `scripts/health_check.py` — 13/13 checks
  PASS.
- **Pilot verification**: a full controlled local pilot session completed
  end-to-end — see
  `docs/38_Pilot_Feedback_pilot-valencia-01_2026-07-17.md`.

## Known Limitations

See MASTER_SPEC.md Section 44, docs/33's "Known Gaps" (as refined above),
and `docs/38_Pilot_Feedback_pilot-valencia-01_2026-07-17.md`'s "Non-Blocking
Findings" for the complete, current list.

## Open Issues

See `notes/Questions.md` for the live, current queue of unresolved
decisions, each tagged with which document it blocks.
