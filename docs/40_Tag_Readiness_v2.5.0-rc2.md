# 40 — Tag Readiness Report: v2.5.0-rc2

Records every check performed before creating the local annotated tag
`v2.5.0-rc2`. **`v2.5.0-rc1` remains unchanged and immutable** — its tag
still points at commit `138c8743b7f6fe23a6f74bff0d47847752ed1316`; this
document and the RC2 tag are new, additive artifacts, not a rewrite of RC1.

## Why RC2 Exists

A controlled local pilot session
(`docs/38_Pilot_Feedback_pilot-valencia-01_2026-07-17.md`) ran the full
documented pilot workflow against RC1 exactly as shipped (tag `v2.5.0-rc1`,
commit `138c8743`). It found one real, user-visible defect — apartment
images never rendered in a real browser for demo-connector results — which
was reproduced, fixed, tested, and committed in the same session
(`b013ad1`). RC2 packages that fix plus the pilot feedback documentation
into a new, separately-tagged release candidate.

## Verified Branch

`release/v2.5-rc1` — confirmed via `git branch --show-current`.

## Verified Commit (Pre-Finalization)

`6f464d7439d41ceaaca6ed28fe591c46aa38da64` ("Record pilot-valencia-01
session feedback") — confirmed via `git rev-parse HEAD`. Built on:
- `b013ad10440ff4ac76232309000af263833bb379` — "Fix broken apartment images
  for demo/fixture connectors" (the real defect fix)
- `138c8743b7f6fe23a6f74bff0d47847752ed1316` — the RC1 tag target, unchanged

**This is not the RC2 tag target.** Per this release's own Phase 12/13
instructions, the tag targets the finalization commit created on top of
this one (adding this document, the RC2 manifest, release notes, and
CHANGELOG/VERSION updates), not this commit itself.

## Commit Content Review

Both commits since the RC1 tag were reviewed and confirmed to contain only
their stated scope, nothing else:

- `b013ad1`: `src/web/routes/apartments.py` (new media route),
  `src/web/templates/apartments/detail.html` (template fix),
  `tests/web/test_routes.py` (4 new regression tests). 3 files, 97
  insertions, 4 deletions.
- `6f464d7`: `docs/38_Pilot_Feedback_pilot-valencia-01_2026-07-17.md` only.
  1 file, 79 insertions.

No unrelated changes, no scope creep, no fixes to any of the six
non-blocking pilot findings (correctly deferred, none proved
release-blocking).

## Clean-Tree Status

`git status --porcelain` returned nothing — clean working tree, confirmed
before starting RC2 work.

## Full Test Result

`python -m unittest discover -s tests -t .`:

```
Ran 1312 tests in 273.564s

OK
```

**1312 tests, 0 failures, 0 errors, 0 skipped** — 1308 carried over from RC1
plus 4 new image-serving regression tests
(`tests/web/test_routes.py::ApartmentImageServingTests`).

## Health-Check Result

`python scripts/health_check.py` — **13/13 PASS**, 0 WARN, 0 FAIL. Identical
result to RC1; nothing in the RC2 changes affects any health check.

## Migration Result

11 migrations present and applied, unchanged from RC1 — the RC2 fix is a
web-layer route/template change only, no schema change.

## Dashboard Startup

Confirmed live in a real browser: `GET /` returns 200, real dashboard
content renders (System Health page, apartment counts, etc.) via the
already-running Flask dev server on `http://localhost:5000`.

## Image-Route Security Result

The new `/apartments/<apartment_id>/media/<filename>` route was
specifically re-verified against the exact real running server (not just
the test suite):

| Case | Result |
|---|---|
| Valid, existing image file | 200, correct `Content-Type` (e.g. `image/png`) |
| Path traversal, URL-encoded forward slashes (`..%2F..%2F..%2Fetc%2Fpasswd`) | 404 |
| Path traversal, URL-encoded backslashes (`..%5C..%5C..%5Cwindows%5Cwin.ini`) | 404 |
| Missing/nonexistent filename | 404 |
| Error response body | plain 404 template — no filesystem path disclosed |

The route reuses the existing `WebSecurity.safe_join()` path-traversal
guard rather than inventing new security logic — the same helper already
established (but previously unused) in `security.py` since Step 16. **PASS.**

## Files Created or Updated for RC2

- `VERSION` — `2.5.0-rc1` → `2.5.0-rc2`
- `CHANGELOG.md` — new `[2.5.0-rc2]` entry added above `[2.5.0-rc1]` (RC1's
  own entry left untouched)
- `RELEASE_NOTES_v2.5-rc2.md` — new
- `release/v2.5.0-rc2-manifest.json` — new
- `docs/40_Tag_Readiness_v2.5.0-rc2.md` — this document
- `docs/37_Pilot_Operations_Guide.md` — version reference bumped, RC2/pilot-example cross-references added
- `docs/38_Pilot_Feedback_Template.md` — version field made generic (was hardcoded to `2.5.0-rc1`), cross-reference to the completed example added

## Known Limitations

Unchanged in substance from RC1, with six additions/refinements discovered
during the pilot session, none release-blocking:

1. `walking_distance`/`public_transport_time` filters always exclude every
   demo-connector apartment (they have no coordinates at all), not merely a
   score-vs-minutes semantic mismatch.
2. `currency` filter always excludes demo-connector apartments (never
   populated by demo connectors) — same category as the pre-existing
   `property_type` gap.
3. Real monitoring runs against demo connectors can never produce a genuine
   price/availability/new-match change event, at any number of repeated
   runs — demo fixtures are 100% static.
4. Geographic-analysis section renders a raw Python dict repr instead of a
   clean "not available" message when no geo data exists. Cosmetic.
5. Duplicate saved-search names are allowed with no uniqueness warning.
6. `config/pilot.example.json`'s example budget (350-750 EUR) returns zero
   results against actual demo fixture prices (950-2600 EUR).

None of these were fixed this release, per this release's own explicit
instruction not to fix non-blocking findings unless proven
release-blocking — none were.

## Remaining Release Blockers

**None identified.**

## Tag Recommendation

**GO**, conditional on the Phase 12 finalization commit ("Prepare
v2.5.0-rc2 release candidate") completing cleanly and a post-commit full
suite re-run also showing 0 failures: create the local annotated tag
`v2.5.0-rc2` pointing at that finalization commit. Do not push the tag; do
not merge `release/v2.5-rc1` into `main` or `platform-v1`; do not move,
delete, or recreate `v2.5.0-rc1`.

## Related Documents

- [39_Tag_Readiness_v2.5.0-rc1.md](39_Tag_Readiness_v2.5.0-rc1.md)
- [38_Pilot_Feedback_pilot-valencia-01_2026-07-17.md](38_Pilot_Feedback_pilot-valencia-01_2026-07-17.md)
- [33_Release_Candidate_Acceptance.md](33_Release_Candidate_Acceptance.md)
- [../release/v2.5.0-rc2-manifest.json](../release/v2.5.0-rc2-manifest.json)
