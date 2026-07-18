# 42 — Version 2.6 Acceptance Report

**Branch:** `feature/v2.6`
**HEAD at time of verification:** `a8a5833` — "Version 2.6.3: Add config-file loader for the New Search dashboard form"
**Working tree:** clean throughout.

This is Phase 3 of the Version 2.6 rollout (docs/41_Version_2.6_Planning.md) —
integration verification across all five committed milestones, run against
both a fresh temporary database (automated tests) and the real, long-lived
local project database (live dashboard) to catch anything a fresh-DB test
suite alone wouldn't. No code was changed during this phase; no release
candidate, tag, push, or merge was created.

## Completed Milestones

| Milestone | Commit | Summary |
|---|---|---|
| 2.6.1 — Pilot Materials Correctness | `1ae6ef4` | Fixed pilot config's budget/currency/proximity example values; clean geo-analysis "Not available" message instead of raw dict repr. |
| 2.6.2 — Demo Fixture Realism | `7af5480` | Populated demo connector fixtures with real currency/property_type/coordinates. |
| 2.6.5 — Saved-Search Name Validation | `464ce7a` | Rejects duplicate saved-search names at creation time only, never retroactively. |
| 2.6.4 — Monitoring Test Fixture Variation | `be28d1e` | Added a deterministic "week 2" demo fixture snapshot + swap mechanism proving real monitoring change-detection end-to-end. |
| 2.6.3 — Configuration Loading | `a8a5833` | Added a config-file loader to the New Search dashboard form. |

## Test Results

Full suite run twice during this phase (once before the live dashboard
session, once mid-session): **1344 tests, 0 failures, `OK`** both times
(231–303s).

## Health Check

`python scripts/health_check.py`: **13/13 PASS**, both runs. 11 migrations
applied, 3 connectors registered (`demo_platform`, `demo_platform_two`,
`rentcast`), console/file notification channels ready, haversine geo
provider registered, localhost-only binding confirmed.

## Migration Verification (Fresh Database)

Constructed a brand-new `Database` against a temporary path with no prior
state. All 11 migrations (`0001`–`0011`) applied cleanly in order, producing
54 tables. Confirms the schema is reproducible from nothing, not just
consistent with the real project database's already-migrated history.

## Backup and Restore Verification

`tests/scripts/test_backup_restore.py`: **10/10 pass**, all against temporary
paths (backup creation + manifest, secret exclusion, compressed archives,
checksum/integrity verification, corruption detection, restore to an
alternate location, restore-then-boot, historical-data preservation,
non-empty-destination refusal without `--force`). Additionally ran a live,
standalone backup → verify → restore round-trip against fully isolated temp
paths outside the test suite: a real `Platform` row inserted, backed up,
verified (`ok=True`, `database_integrity_ok=True`), restored, and confirmed
present in the restored database.

## CLI Verification

All three CLI entry points start and print `--help` correctly, exit code 0:
`python -m src.ui.cli`, `python -m src.ui.monitoring_cli`,
`python -m src.ui.notification_cli`. No existing flag was added, removed, or
renamed (Milestone 2.6.3's own backward-compatibility requirement) — the
main search CLI's flag set is byte-for-byte the same set that existed before
Version 2.6.

## Dashboard Verification

Started the real Flask dev server (`src.web.application`) locally. Serving
`200`s from first request. No startup errors or warnings beyond the expected
"development server" notice.

## End-to-End Workflow (Live, Real Browser)

Driven against the real local dashboard and the real, long-lived project
database (not a fresh temp DB — deliberately, to exercise state a fresh
database wouldn't have):

1. **Config-file upload UI** — the New Search form's new "Load from a config
   file" file input renders correctly at the top of the form. (The actual
   *upload* was verified via the real Flask test client rather than browser
   automation — browsers block scripted writes to `<input type="file">` for
   security, so no automation tool can drive a real file selection. See
   "Config-Loader Regression Verification" below for the equivalent proof.)
2. **Search** — submitted City=`Example City`, Maximum Price=`1500` through
   the manual form fields.
3. **Filtering** — job completed; results correctly narrowed from the full
   demo catalog to the 4 apartments priced ≤ 1500 (950/1050/1100/1450),
   excluding the 2100/2600 listings.
4. **Ranking** — every result carries a real score, confidence, and
   human-readable positive-factor explanation (e.g. "Excellent price: $950/mo
   vs $1542/mo city average (-38%)").
5. **Apartment detail page** — opened a result; Overview table renders real
   observed data (price, status, bedrooms, address, platform, timestamps).
6. **Images** — the image gallery renders a real downloaded image byte-for-
   byte from the same-origin media route (the RC2 fix from Version 2.5),
   confirmed visually via screenshot.
7. **Geographic analysis clean message** — this specific apartment has no
   coordinates recorded (see known limitation A below); the detail page
   correctly shows "Not available — no distances or nearby places could be
   computed for this apartment (coordinates unavailable)" — the Milestone
   2.6.1 fix, confirmed live, not the pre-2.6.1 raw dict repr.
8. **Saved search** — created "Phase 3 Verification Watch" against
   `Example City`; appears correctly alongside the two pre-existing
   `pilot-valencia-01` duplicate-named saved searches from the original v2.5
   pilot session (proving Milestone 2.6.5's uniqueness check is creation-time
   only and never breaks pre-existing duplicate data on read).
9. **Monitoring run 1** — "Run now" on the new saved search: status
   `partial`, 3 events recorded.
10. **Monitoring run 2** — "Run now" again immediately: status `partial`, 2
    events recorded (fewer than run 1, not equal/growing) — live confirmation
    of deduplication, consistent with
    `tests/monitoring/test_engine.py::test_rerunning_unchanged_fixtures_does_not_fabricate_apartment_change_events`.
11. **Notification preview** — previewed the queued events for a new
    console+file preference before delivery; real event list shown.
12. **Notification delivery** — "Deliver pending notifications now":
    "Processed 5 delivery attempt(s)"; delivery history shows real
    `delivered` entries. Confirmed 3 real file-channel artifacts written to
    `output/notifications/` with filenames matching the delivered IDs
    exactly.
13. **Feedback** — recorded a `shortlisted` event on the apartment from step
    5; "Feedback recorded" confirmed, redirected to a live-updated preference
    profile.
14. **Preference explanation** — opened "Explain" for `internet_included`:
    real evidence list (four `filter_selected` observations with real
    timestamps) and a real adjustment history with working "Undo" links.
15. **Discovery** — submitted a manual discovery run for Valencia; "Discovery
    run started" confirmed with a real run id.
16. **JSON API** — `GET /api/v1/health` returned real structured health data
    (connector health, monitoring health for both saved searches created in
    this session, notification channel health showing the exact delivery
    counts from step 12). `GET /api/v1/apartments/<id>` returned the full
    apartment detail payload including the `shortlisted` feedback event just
    recorded in step 13.

## Config-Loader Regression Verification

`tests/web/test_forms.py::ConfigLoaderTests`: **9/9 pass**, including
`test_number_of_rooms_and_room_type_are_never_translated` — the regression
test locking in the one real defect found and fixed during Milestone 2.6.3's
own implementation (see that milestone's commit message and
`src/web/forms/config_loader.py`'s module docstring): the config's
`property_and_room.number_of_rooms`/`.room_type` fields describe a different
concept than the registered `number_of_rooms` filter (exact total-bedroom
match) and must never be auto-translated onto it. `test_the_shipped_pilot_example_config_loads_without_error`
and `tests/web/test_routes.py::ConfigFileUploadTests::test_uploading_the_shipped_pilot_config_starts_a_real_search`
together prove the real, shipped `config/pilot.example.json` uploads through
the real route and produces real, non-zero, correctly-filtered demo results
(4/4 matched under its 900–2700 budget).

## Security Verification

- **CSRF** — `tests/web/test_security.py::CsrfProtectionTests`: 5/5 pass
  (valid token accepted, missing/wrong token rejected, GET exempt, JSON API
  exempt).
- **Path traversal** — `PathTraversalRouteTests` + `SafeJoinTests`: 3/3 pass;
  `tests/web/test_routes.py::ApartmentImageServingTests::test_media_route_rejects_path_traversal`
  (both `..%2F` and `..%5C` encodings) also passes.
- **Safe media serving** — same-origin media route confirmed live (workflow
  step 6) and via `test_apartment_media_route_serves_the_downloaded_image_bytes`.
- **Safe upload handling** — the new config-file upload path rejects
  malformed JSON, a JSON array instead of an object, a missing `search` key,
  a missing location, and out-of-range values, all via the same
  `WebValidationError` path form submission already uses (no new failure
  mode, no partial state left behind). Additionally confirmed live: invalid
  (non-UTF-8) byte content raises `WebValidationError("Config file must be
  UTF-8 encoded")` rather than crashing. Upload size is bounded by the
  existing global `MAX_CONTENT_LENGTH` (5 MiB), which Flask enforces on every
  request body including multipart uploads — no new size-limit code needed.
- **No secrets tracked** — `git ls-files` scanned for `.env`, `secret`,
  `credential`, `.key`, `.pem` patterns: none found.
- **No runtime artifacts tracked** — `git ls-files` scanned for `data/`,
  `output/`, `.db` paths: only `.gitkeep` placeholders found, no real
  database or generated files.
- **Request size limits, security headers, localhost binding, safe URL
  validation** — all pass via the existing `tests/web/test_security.py`
  suite (15/15).

## Known Limitations (Non-Blocking)

**A. Pre-2.6.2 local databases don't retroactively gain currency/property_type/coordinates.**
`apartment_repository.update_apartment_state()`/`.update_apartment_details()`
deliberately only refresh price/status/title/description on re-observation —
a Migration-0004-era design (predates this entire session), not a Version
2.6 regression. Surfaced live in this phase because the real project
database has demo apartments first observed on 2026-07-14, before Milestone
2.6.2 existed. A **fresh** database (every automated test, and any new pilot
or production deployment) shows the real currency/property_type/coordinates
values correctly, as proven throughout Milestones 2.6.2/2.6.3's own test
suites. No fix required for Version 2.6; a future milestone could evaluate
whether re-observation should also refresh these fields.

**B. The saved-search "Run now" button's job-status page 404s on
auto-redirect after a monitoring run completes**, even though the underlying
monitoring run itself completes correctly (confirmed via the saved-search
detail page and the JSON API in workflow steps 9–10 and 16). This is
pre-existing `job_status.html` client-side redirect behavior from Version
2.5 Step 16, untouched by any Version 2.6 milestone. Worth a follow-up
ticket; not part of Version 2.6's scope.

Neither limitation is release-blocking: both predate Version 2.6, neither
affects a fresh installation, and neither was introduced or worsened by any
of the five committed milestones.

## Release Blockers

None.

## Final Acceptance Decision

**PASS**
