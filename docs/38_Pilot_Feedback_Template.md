# 38 — Pilot Feedback Template

Version 2.5 Step 18. Copy this file per pilot session (or per defect — see
`docs/37_Pilot_Operations_Guide.md` section 17) and fill in every field
honestly. Leave a field blank and write "not observed" or "N/A" rather than
guessing — this platform's own discipline throughout its documentation is to
never fabricate a value, and pilot feedback should hold to the same
standard.

## Session Identification

- **Pilot session ID**: _(e.g., `pilot-valencia-01` — matches the
  profile-id/label used throughout the session, per docs/37 section 12-13)_
- **Date**: _(YYYY-MM-DD)_
- **Pilot operator**: _(name or handle)_
- **Platform version tested**: 2.5.0-rc1
- **Interface used**: _(web dashboard / CLI / both)_

## Search Details

- **Search request** _(location + criteria entered, or the exact CLI
  command)_:
- **Number of platforms attempted**: _(how many connectors were enabled for
  this search)_
- **Number of platforms accessible**: _(how many actually returned results
  without error)_

## Result Quality

- **Result count**: _(total apartments returned)_
- **Relevant result count**: _(results the operator judged actually matched
  their stated criteria)_
- **Irrelevant result count**:
- **Missing important fields**: _(e.g., price, images, property_type — name
  the specific field and apartment)_
- **Broken original URLs**: _(list any apartment whose original listing URL
  didn't load or was wrong)_
- **Image quality**: _(present/absent, resolution, relevance — free text)_
- **Price accuracy**: _(did the displayed price match what you'd expect from
  the fixture/source; note "N/A — demo fixture" if not applicable)_
- **Availability accuracy**: _(same caveat as price accuracy)_

## Feature Usefulness (1-5, 5 = most useful, or "N/A")

- **Ranking usefulness**:
- **Filter usefulness**:
- **Geographic-analysis usefulness**:
- **Report usefulness** (HTML/JSON report):
- **Dashboard usability**:

## Performance

- **Runtime**: _(wall-clock time from submitting the search to seeing
  results)_
- **Errors encountered**: _(exact error text/traceback, or "none")_
- **Manual work still required**: _(anything the operator had to do outside
  the platform to get a usable answer — e.g., manually checking a listing
  site directly)_

## Defect Detail (if applicable — leave blank for a general session report)

- **Expected result**:
- **Actual result**:
- **Severity**: _(blocker / major / minor / cosmetic)_
- **Reproduction steps**:
  1.
  2.
  3.
- **Screenshots or artifact references**: _(file paths under `output/`, a
  saved HTML/JSON report, or an attached screenshot)_

## Overall Recommendation

- **Overall recommendation**: _(ready for wider pilot / needs fixes before
  wider pilot / not ready — with one sentence why)_
- **Anything else worth noting**:

## Related Documents

- [37_Pilot_Operations_Guide.md](37_Pilot_Operations_Guide.md)
- [33_Release_Candidate_Acceptance.md](33_Release_Candidate_Acceptance.md)
