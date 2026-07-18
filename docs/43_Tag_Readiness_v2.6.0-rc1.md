# 43 — Tag Readiness Report: v2.6.0-rc1

Records every check performed before creating the local annotated tag
`v2.6.0-rc1`. **Both `v2.5.0-rc1` and `v2.5.0-rc2` remain unchanged and
immutable** — their tags still point at commits `138c8743b7f6fe23a6f74bff0d47847752ed1316`
and `51c5d4bdae95626bb8d70553dd654dec7b3b2289` respectively; this document
and the v2.6.0-rc1 tag are new, additive artifacts, not a rewrite of either.

## Why v2.6.0-rc1 Exists

`docs/41_Version_2.6_Planning.md` (approved 2026-07-17) proposed five small,
focused milestones closing essentially every non-blocking finding from the
v2.5 pilot session, plus the "no config-file loader" gap that session's own
manual-transcription workflow made obvious. All five milestones were
implemented, tested, and committed on `feature/v2.6` (branched from
`platform-v1` at `v2.5.0-rc2`'s commit); Phase 3 integration verification
(`docs/42_Version_2.6_Acceptance_Report.md`) then confirmed **PASS** with no
release blockers. This document records the final pre-tag verification for
the resulting release candidate.

## Verified Branch

`feature/v2.6` — confirmed via `git branch --show-current`.

## Verified Commit (Pre-Finalization)

`8f7b0e4ad835fbfb8d7c8371905584632c4fd8f7` ("Approve Version 2.6
implementation plan," cherry-picked from `main` — see "A Note on
`docs/41`'s Branch History" below). Built on:

- `3e9ff1e3fcaf0a1cb9e86959c6e2bdf3347a7a84` — "Add Version 2.6 acceptance
  report (Phase 3 integration verification)"
- `a8a5833e7b064cac605b62163a047e5b62c4d53e` — "Version 2.6.3: Add
  config-file loader for the New Search dashboard form"
- `be28d1eb102a725f8ed83627ed391fb5a423b0d2` — "Version 2.6.4: Add week-2
  demo fixture snapshot for monitoring change detection"
- `464ce7a097543e636319f032515d4b3633c02d9f` — "Version 2.6.5: Add
  saved-search name uniqueness validation"
- `7af54802388940a2dac640dacec9a6089829136b` — "Version 2.6.2: Add
  currency, property type, and coordinates to demo fixtures"
- `1ae6ef4e6e2986af29849a9641f19cfb6733e126` — "Version 2.6.1: Improve
  pilot configuration and geographic analysis UI"
- `51c5d4bdae95626bb8d70553dd654dec7b3b2289` — the `v2.5.0-rc2` tag target,
  unchanged

**This is not the v2.6.0-rc1 tag target.** Per this release's own
instructions, the tag targets the finalization commit created on top of
this one (adding this document, the RC1 manifest, release notes, and
CHANGELOG/VERSION updates), not this commit itself.

## A Note on `docs/41`'s Branch History

`docs/41_Version_2.6_Planning.md` was originally approved and committed on
`main` (commit `faf1d8e`), *before* `feature/v2.6` was branched from
`platform-v1` — a topology gap discovered and flagged during Milestone
2.6.2's own work (it never made it onto this branch). Rather than ship a
release candidate whose own roadmap document is missing from its tagged
tree, that single commit was cherry-picked onto `feature/v2.6` as part of
this RC1 preparation (`8f7b0e4`, identical file content, new commit hash).
No other content from `main` was pulled in.

## Commit Content Review

Every commit since the `v2.5.0-rc2` branch point was reviewed and confirmed
to contain only its stated scope:

| Commit | Files | Insertions/Deletions |
|---|---|---|
| `1ae6ef4` (2.6.1) | 4 | +206/-7 |
| `7af5480` (2.6.2) | 11 | +219/-29 |
| `464ce7a` (2.6.5) | 4 | +84/-1 |
| `be28d1e` (2.6.4) | 6 | +256/-7 |
| `a8a5833` (2.6.3) | 6 | +320/-20 |
| `3e9ff1e` (acceptance report) | 1 | +209/-0 |
| `8f7b0e4` (docs/41 cherry-pick) | 1 | +256/-0 |

No unrelated changes, no scope creep, no fixes beyond each milestone's
stated boundary — each commit's diff was individually reviewed for
unrelated edits, debug code, temporary files, and formatting drift before
being committed (see each milestone's own commit-time verification, already
performed and reported in this session).

## Clean-Tree Status

`git status --porcelain` returned nothing before starting RC1 file
creation — clean working tree, confirmed.

## Full Test Result

`python -m unittest discover -s tests -t .`:

```
Ran 1344 tests in 282.594s

OK
```

**1344 tests, 0 failures, 0 errors, 0 skipped** — 1312 carried over from
v2.5.0-rc2, plus 32 new across the five milestones (5 for 2.6.5, 3 for
2.6.4, 11 for 2.6.3, plus 2.6.1/2.6.2's own additions already reflected in
the 1312→1344 delta).

## Health-Check Result

`python scripts/health_check.py` — **13/13 PASS**, 0 WARN, 0 FAIL. Same 11
migrations, same 3 connectors registered, same notification channel
readiness as v2.5.0-rc2.

## Migration Result

11 migrations present and applied, unchanged from v2.5.0-rc2 — every
Version 2.6 milestone was additive data (fixture fields, a new fixture
snapshot file, application-layer validation) or a new module
(`src/web/forms/config_loader.py`); none required a schema change, matching
`docs/41`'s own "Database and Migration Impact: None" assessment.
Independently re-verified against a brand-new temporary database during
Phase 3 (`docs/42`): all 11 migrations apply cleanly from nothing, 54
tables produced.

## Config-File Loader Security and Regression Result

The new config-file upload path (Milestone 2.6.3) was specifically
re-verified in Phase 3 (`docs/42`):

| Case | Result |
|---|---|
| Valid, shipped `config/pilot.example.json` | Loads and starts a real search with real, non-zero, correctly-filtered results |
| Malformed JSON | `WebValidationError`, same failure path as an invalid form field |
| JSON array instead of an object | `WebValidationError` |
| Missing `search` key | `WebValidationError` |
| Missing location | `WebValidationError` (same message a manually-filled form with no location would produce) |
| Out-of-range price | `WebValidationError` (reuses the existing `parse_optional_float(minimum=0.0)` check, no new validation logic) |
| Non-UTF-8 byte content | `WebValidationError("Config file must be UTF-8 encoded")`, no crash |
| `property_and_room.number_of_rooms`/`.room_type` present in the config | Never translated onto a filter (the real defect found and fixed during this milestone — see `src/web/forms/config_loader.py`'s docstring) |

Upload size is bounded by the existing global `MAX_CONTENT_LENGTH` (5 MiB),
enforced by Flask on every request body including multipart uploads — no
new size-limit code was written. No existing CLI flag or form field was
added, removed, or renamed. **PASS.**

## Dashboard Startup

Confirmed live in a real browser during Phase 3: the real Flask dev server
started cleanly, served real `200`s from first request, and a full 16-step
end-to-end workflow (search, filtering, ranking, apartment detail, images,
clean geo-analysis message, saved search, monitoring x2 with live
deduplication, notification preview/delivery, feedback, preference
explanation, discovery, JSON API) completed successfully — see
`docs/42_Version_2.6_Acceptance_Report.md` for the full transcript.

## Files Created or Updated for v2.6.0-rc1

- `VERSION` — `2.5.0-rc2` → `2.6.0-rc1`
- `CHANGELOG.md` — new `[2.6.0-rc1]` entry added above `[2.5.0-rc2]` (all
  prior entries left untouched)
- `RELEASE_NOTES_v2.6.0-rc1.md` — new
- `release/v2.6.0-rc1-manifest.json` — new
- `docs/43_Tag_Readiness_v2.6.0-rc1.md` — this document

## Known Limitations

Unchanged in substance from v2.5.0-rc2 except for the closures and
additions below, none release-blocking:

**Closed this release:**
1. `config/pilot.example.json`'s example budget no longer returns zero
   results against demo fixtures (2.6.1).
2. The geographic-analysis section no longer renders a raw dict repr
   (2.6.1).
3. `currency`/`property_type` filters can now be meaningfully exercised
   against demo connector fixtures (2.6.2).
4. Duplicate saved-search names are now rejected at creation (2.6.5).
5. Monitoring change-detection is now genuinely demonstrable against demo
   connectors via the week-2 fixture snapshot (2.6.4).
6. `config/pilot.example.json` is no longer purely a manual-transcription
   reference — the dashboard can load it directly (2.6.3).

**Refined (partially closed):**
7. Proximity filters (`walking_distance`/`public_transport_time`) still
   need a curated `city_center`/`public_transport` reference point for the
   exact search location — populating coordinates (2.6.2) was necessary
   but not sufficient; nothing seeds that curated reference automatically.

**New, discovered during Phase 3 (both pre-existing, neither a Version 2.6
regression):**
8. A local database seeded before Milestone 2.6.2 does not retroactively
   backfill currency/property_type/coordinates on re-observation (a
   Migration-0004-era design choice). Fresh databases are unaffected.
9. The saved-search "Run now" job-status page's client-side auto-redirect
   404s after a monitoring run completes, even though the run itself
   completes correctly. Pre-existing Version 2.5 Step 16 behavior.

**Unchanged, still open:**
10. No commercial rental platform connector exists in this release
    (blocked by Terms of Service — an explicit business/legal decision,
    not an engineering one).

None of items 7-10 were fixed this release, per this release's own explicit
scope boundaries (`docs/41` Section 5) — none proved release-blocking.

## Remaining Release Blockers

**None identified.**

## Tag Recommendation

**GO**, conditional on the Phase 4 finalization commit ("Prepare
v2.6.0-rc1 release candidate") completing cleanly and a post-commit
clean-tree check also passing: create the local annotated tag
`v2.6.0-rc1` pointing at that finalization commit. Do not push the tag; do
not merge `feature/v2.6` into `platform-v1` or `main`; do not move, delete,
or recreate `v2.5.0-rc1` or `v2.5.0-rc2`.

## Related Documents

- [42_Version_2.6_Acceptance_Report.md](42_Version_2.6_Acceptance_Report.md)
- [41_Version_2.6_Planning.md](41_Version_2.6_Planning.md)
- [40_Tag_Readiness_v2.5.0-rc2.md](40_Tag_Readiness_v2.5.0-rc2.md)
- [39_Tag_Readiness_v2.5.0-rc1.md](39_Tag_Readiness_v2.5.0-rc1.md)
- [33_Release_Candidate_Acceptance.md](33_Release_Candidate_Acceptance.md)
- [../release/v2.6.0-rc1-manifest.json](../release/v2.6.0-rc1-manifest.json)
