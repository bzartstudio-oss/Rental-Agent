# Pilot Feedback — Session `pilot-valencia-01` (2026-07-17)

A completed copy of `docs/38_Pilot_Feedback_Template.md` for the Version
2.5.0-rc1 controlled local pilot session run against commit `b013ad1`
(`release/v2.5-rc1`), immediately after the GitHub backup of the release
candidate. The blank template itself is left untouched for reuse in future
pilot sessions, per its own stated purpose.

## Session Identification

- **Pilot session ID**: `pilot-valencia-01`
- **Date**: 2026-07-17
- **Pilot operator**: Claude (agent-run pilot, per user instruction — no human operator involved in this specific session)
- **Platform version tested**: 2.5.0-rc1 (branch `release/v2.5-rc1`, commit `b013ad1` after the in-session bug fix; started from `138c8743`, the tagged commit)
- **Interface used**: Both — web dashboard (real browser, `http://localhost:5000`) for the search/results/detail workflow, CLI for monitoring/notifications/feedback/discovery

## Search Details

- **Search request**: Valencia, Spain (`country=Spain, region=Valencian Community, city=Valencia, postal_area=46120`), budget 900–2700 (adjusted from `config/pilot.example.json`'s example 350–750 — see Defect Detail), furnished + internet-included checked, platforms `demo_platform` + `demo_platform_two`, feedback_mode=suggested, ranking default profile, saved as `pilot-valencia-01`
- **Number of platforms attempted**: 3 (`demo_platform`, `demo_platform_two`, `rentcast` — rentcast intentionally left unauthenticated, no API key)
- **Number of platforms accessible**: 2 of 3 (`demo_platform`, `demo_platform_two` succeeded; `rentcast` failed as expected — no `RENTCAST_API_KEY` configured, consistent with the pilot's own documented scope)

## Result Quality

- **Result count**: 6 apartments
- **Relevant result count**: 6 (all within the corrected budget)
- **Irrelevant result count**: 0
- **Missing important fields**: every demo-connector apartment is missing `currency`, `property_type`, and `coordinates` — all honestly labeled "not available"/"Missing: ..." in the UI, not fabricated. This is expected per the platform's own documented demo-connector limitations, not a new finding.
- **Broken original URLs**: none — all 6 "Original listing ↗" links resolved to valid fixture URLs (e.g. `https://example.com/demo-platform/listings/demo-002`)
- **Image quality**: **initially broken, now fixed during this session** — see Defect Detail below. After the fix, images render correctly (confirmed `naturalWidth`/`naturalHeight` non-zero in the live browser).
- **Price accuracy**: N/A — demo fixture (prices are the connector's own static, deterministic values: 950–2600)
- **Availability accuracy**: N/A — demo fixture

## Feature Usefulness (1-5, 5 = most useful)

- **Ranking usefulness**: 4 — clear score/confidence, honest "Excellent price: $X/mo vs $Y/mo city average" explanations
- **Filter usefulness**: 3 — works well for data-backed filters (price, amenities-as-dormant-passthrough); two filters (`walking_distance`, `public_transport_time`) are unusable against demo data (see Defect Detail) and one (`currency`) unexpectedly zeroes results
- **Geographic-analysis usefulness**: 2 — honestly reports "not available" (correct, no fabrication) but the raw dict repr `{'distances': {}, 'nearby': {}}` is a confusing, unpolished way to say so (see Defect Detail — cosmetic)
- **Report usefulness (HTML/JSON report)**: 4 — both formats generated correctly every run, real ranked apartment data, referenced consistently from CLI/notification output
- **Dashboard usability**: 4 — clear navigation, honest missing-data labeling throughout, job-progress page auto-refreshes correctly

## Performance

- **Runtime**: not precisely instrumented this session; consistent with `docs/36_Performance_Baseline.md`'s own measured multi-platform search time (~2.5s for `demo_platform` + `demo_platform_two`) — no perceptible difference observed
- **Errors encountered**: none uncaught/unhandled; the one real defect found (broken images) failed silently in the browser (no error surfaced to the user) rather than throwing
- **Manual work still required**: none for the core search→review→feedback loop; monitoring's price/availability change detection cannot be demonstrated at all against demo connectors (see Defect Detail — a testability limitation, not manual user work)

## Defect Detail — Item 1 (Fixed This Session)

- **Expected result**: apartment detail page's "Image gallery" section displays each listing's photo
- **Actual result**: every image was completely broken (blank/broken-image icon) for every demo-connector apartment — `ApartmentImage.source_url` is a `file://` path (fixture pages are loaded from local disk), which no real browser will load from an `http://` page; confirmed via `img.naturalWidth === 0` in the live browser
- **Severity**: major (a documented, advertised feature — "verify images" — silently didn't work at all for the platform's own primary demo/pilot pathway)
- **Reproduction steps**:
  1. Run any search against `demo_platform`/`demo_platform_two` via the web dashboard
  2. Open any apartment's detail page
  3. Observe the "Image gallery" section — the `<img>` tag's `src` is a `file:///...` URL; the browser reports `naturalWidth: 0`
- **Resolution**: fixed in commit `b013ad10440ff4ac76232309000af263833bb379` — added a same-origin `/apartments/<id>/media/<filename>` route (reusing the already-downloaded `ApartmentImage.local_path` and the existing `WebSecurity.safe_join()` path-traversal guard), updated the detail template to use it. 4 new regression tests added (`tests/web/test_routes.py::ApartmentImageServingTests`). Full suite: 1312 tests, 0 failures, both before and after the fix's own verification runs. **The `v2.5.0-rc1` tag was not moved** — it still points at `138c8743` (pre-fix). **An RC2 tag may be warranted** if this fix should be part of the tagged release; left to human judgment per the mission's instructions.
- **Screenshots or artifact references**: verified live in the browser pane (`naturalWidth: 64, naturalHeight: 64` after the fix, at `http://localhost:5000/apartments/cf74de96-0f52-43c7-abaa-31284eded72a/media/0.png`)

## Non-Blocking Findings (Documentation/Config Only — No Code Changed)

1. **`config/pilot.example.json`'s example budget (350–750 EUR) returns zero results against the demo connector fixture data (actual prices: 950–2600 EUR).** A pilot user following the shipped example literally gets an empty result on their very first try. Recommend widening the example range in a future doc revision.
2. **`config/pilot.example.json`'s example `currency: "EUR"` filter always excludes every demo-connector apartment**, since demo connectors never populate `Apartment.currency` (confirmed via the filter's own code comment: "Populated by RentCast; demo connectors leave it unset") — the same category of gap as the already-documented `property_type` limitation (docs/33 Known Gap #3), just not previously called out for `currency` specifically. Recommend removing `currency` from the example or noting it explicitly.
3. **`walking_distance`/`public_transport_time` filters always exclude every demo-connector apartment**, not just because they're a proximity score rather than literal minutes (docs/33 Known Gap #1, already documented) but because demo apartments have **no coordinates at all** (`latitude`/`longitude` are `None` for all 6) — so no proximity score is ever computed for them, under *any* threshold value. This is a stronger, more consequential version of Known Gap #1 than currently documented. Recommend amending docs/33's wording to make this explicit.
4. **Real monitoring runs against demo connectors can never produce a genuine `price_decreased`/`price_increased`/`availability_changed`/`new_match` event**, at any number of repeated runs — not just "requires a second observation" (docs/33 Known Gap #4's current wording), but structurally impossible, because demo connector fixtures are 100% static (the same HTML file every time), so two consecutive monitoring runs always observe bit-for-bit identical data. Directly mutating the database's `apartments` table between runs does **not** help, because change detection compares two *search snapshots* (both pulled from the same static fixture), not the live `apartments` table. Confirmed via direct code reading (`src/monitoring/detectors/apartment_change_detector.py::_price_events`/`_availability_events`, both gated on `context.search_comparison`, itself built from two `SearchComparison` snapshots). This is why the existing acceptance test suite (Journey D) and this pilot both had to directly record a synthetic event to test notification delivery at all. Recommend amending docs/33 Known Gap #4 to state this precisely, so a future pilot operator doesn't spend time (as this session did) trying to trigger it via direct database edits.
5. **Geographic-analysis section shows a raw Python dict repr** (`{'distances': {}, 'nearby': {}}`) instead of a clean "not available" message when no geo data exists. Cosmetic only — the underlying honesty (no fabricated data) is correct, just unpolished. Not fixed this session (out of scope per "fix only the defect" — one focused defect was fixed, this is a separate, lower-severity item).
6. **Duplicate saved-search names are allowed** — this session accidentally created two saved searches both named `pilot-valencia-01` (from two form submissions during defect diagnosis) with no warning or uniqueness constraint. Minor UX observation, not investigated further.
7. **Notification channel health page labels untested channels (`email`, `webhook`) as "healthy (0 ok / 0 failed)"** rather than distinguishing "never used" from "confirmed working." Minor wording nit, not investigated further.

## Overall Recommendation

- **Overall recommendation**: **Ready for wider pilot**, with the one real defect found (broken images) already fixed and verified in this same session (commit `b013ad1`, full suite green, tag not moved). The remaining findings are all documentation/example-config accuracy issues and cosmetic polish, not functional defects — none block a real pilot user from completing the full search → review → feedback → monitor → notify workflow.
- **Anything else worth noting**: An RC2 decision is a human call — the fix is real and verified, but per the mission's explicit instructions this agent did not move or recreate the `v2.5.0-rc1` tag. `config/pilot.example.json` and `docs/33`'s Known Gaps section would benefit from the corrections listed above in a future documentation-only patch, whether or not an RC2 code tag is cut.

## Related Documents

- [37_Pilot_Operations_Guide.md](37_Pilot_Operations_Guide.md)
- [38_Pilot_Feedback_Template.md](38_Pilot_Feedback_Template.md)
- [33_Release_Candidate_Acceptance.md](33_Release_Candidate_Acceptance.md)
