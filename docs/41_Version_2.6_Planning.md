# 41 — Version 2.6 Planning

**Status: APPROVED (2026-07-17).** Written after confirming Version 2.5
(v2.5.0-rc2) is fully released, promoted to `main` and `platform-v1`, and
cleaned up (see `docs/40_Tag_Readiness_v2.5.0-rc2.md` and the
release-branch deletion that followed it). This document proposes scope
only — no production code is written or changed by it; implementation
happens on `feature/v2.6`, milestone by milestone.

Grounded in: `MASTER_SPEC.md` (Sections 44-46: Known Limitations, Open
Decisions, Version Roadmap), `RELEASE_NOTES_v2.5-rc2.md`,
`docs/38_Pilot_Feedback_pilot-valencia-01_2026-07-17.md`,
`docs/33_Release_Candidate_Acceptance.md` (Known Gaps), and
`notes/Questions.md`. Every problem cited below traces to one of these real
documents, not a fresh guess.

## 1. Version 2.6 Objective

Close the gap between "what the pilot proved works" and "what the pilot
found confusing or broken," using only fixes and small, well-scoped
improvements that were already identified during Version 2.5's own
acceptance and pilot process — not a new feature sprint. Version 2.6 should
make a *second* pilot session (or the same one, repeated) produce zero
"known-limitation" surprises for the items classified must-have below,
while explicitly not chasing the larger, vendor/legal-dependent items still
sitting in `notes/Questions.md`.

## 2. Problems to Solve

Each traced to a real, already-documented source:

1. **`config/pilot.example.json`'s example values don't work against the
   platform's own demo connectors** (budget 350-750 EUR vs. actual fixture
   prices 950-2600 EUR; `currency: "EUR"` and `walking_distance`/
   `public_transport_time` both unconditionally zero every demo result).
   Source: `docs/38_Pilot_Feedback_pilot-valencia-01_2026-07-17.md`.
2. **There is no config-file loader** — `config/pilot.example.json` is a
   manual-transcription reference only, not something the CLI or dashboard
   can load. Source: same pilot feedback; `docs/37_Pilot_Operations_Guide.md`
   section 9.
3. **Demo connector fixtures never populate `currency`, `property_type`, or
   coordinates**, so three filters and all real geographic analysis are
   permanently unusable against the only connectors that ship
   credential-free. Source: `docs/33` Known Gaps #1/#3, pilot feedback
   findings #2/#3.
4. **Monitoring's own change-detection logic can never fire against demo
   connectors**, at any number of repeated runs, because the fixtures are
   100% static — not a "requires a second observation" issue as originally
   worded, but a structural impossibility with today's fixture design.
   Source: pilot feedback finding #3 (refining `docs/33` Known Gap #4).
5. **The geographic-analysis section renders a raw Python dict repr**
   instead of a human-readable "not available" message. Source: pilot
   feedback finding #5.
6. **Saved-search names are not validated for uniqueness** — this pilot
   session created two saved searches both named `pilot-valencia-01` with
   no warning. Source: pilot feedback finding #6.

## 3. Proposed Milestones

- **Milestone 2.6.1 — Pilot Materials Correctness**: fix items 1 and 5
  above (config example values, geo-analysis rendering). No schema change,
  no new code paths, pure correctness fixes to existing, already-shipped
  surfaces.
- **Milestone 2.6.2 — Demo Fixture Realism**: add `currency`,
  `property_type`, and real `latitude`/`longitude` values to the
  `demo_platform`/`demo_platform_two` fixtures, so the *existing* filters
  and the *existing* `HaversineGeoProvider` can actually run end-to-end
  without a real RentCast key. No new filter logic, no new geo provider —
  just populating fields the data model and engines already support.
- **Milestone 2.6.3 — Configuration Loading**: build the config-file loader
  that item 2 identifies as missing, so `config/pilot.example.json` (or a
  user's own copy) becomes something the CLI/dashboard actually reads,
  rather than a manual-transcription reference.
- **Milestone 2.6.4 — Monitoring Test Fixture Variation**: add a second,
  deterministic "week 2" fixture snapshot for the demo connectors (a real
  but controlled data change: one price change, one availability change,
  one new listing) so monitoring's change-detection can be genuinely
  demonstrated end-to-end without touching monitoring engine logic itself.
- **Milestone 2.6.5 — Saved-Search Name Validation**: add a uniqueness
  check (warn or reject) on saved-search creation, addressing item 6.

## 4. Features Explicitly In Scope

- Correcting `config/pilot.example.json`'s example values (budget, remove
  or caveat `currency`/proximity filters).
- Fixing the geographic-analysis template to render a clean fallback
  message instead of a raw dict repr.
- Populating `currency`, `property_type`, `latitude`, `longitude` on the
  existing demo connector fixtures.
- A config-file loader for the CLI and/or web dashboard (reading a JSON
  file matching `config/pilot.example.json`'s shape).
- A second demo-connector fixture snapshot enabling genuine monitoring
  change-detection demonstrations.
- Saved-search name uniqueness validation.

## 5. Features Explicitly Out of Scope

- **Any real commercial rental-platform connector** (Zillow, Idealista,
  Fotocasa, etc.) — still blocked by each platform's Terms of Service; no
  engineering decision unblocks this, only an explicit legal/business
  approval per `RELEASE_NOTES_v2.5-rc2.md`'s "Blocked by External Access
  Restrictions."
- **Real travel-time/transit-routing integration** (an actual routing API
  replacing the haversine estimate) — a vendor/cost/ToS decision, same
  category as the discovery-provider and notification-channel decisions
  already logged as open in `notes/Questions.md`, not resolved by this
  plan.
- **A real task queue, multi-user authentication, or broader
  production-deployment observability** — all three are explicitly logged
  as open, deployment-target-dependent decisions in `notes/Questions.md`
  and `MASTER_SPEC.md` Section 45; none are answered or assumed here.
- **Redesigning the `currency` filter's fail-closed semantics** — evaluated
  and deliberately not changed this version (see Section 12, Risks).
- **Any new product feature** not already named as a known limitation from
  Version 2.5's own acceptance/pilot process.

## 6. Architectural Impact

None. Every in-scope item is additive data (fixture fields), a small new
loader module reusing the existing `WebConfiguration`/CLI-argument pattern,
a template fix, and a validation check — no new engine, no new package,
no change to `WebServiceFacade`'s role as the single call surface.

## 7. Database and Migration Impact

None expected. `currency`/`property_type`/`latitude`/`longitude` columns
already exist on `apartments` (populated by RentCast today, simply left
`NULL` by demo connectors) — Milestone 2.6.2 populates existing columns via
fixture data, it does not add columns. Saved-search name uniqueness
(Milestone 2.6.5) can be enforced at the application layer without a schema
change (or, if a real unique index is preferred, one small additive
migration — a decision for implementation time, not this planning
document).

## 8. Security Considerations

None of the in-scope items touch authentication, CSRF, path handling, or
any existing security control. The config-file loader (Milestone 2.6.3)
must reuse the same validation-at-the-boundary discipline already
established in `src/web/forms/validation.py` (reject unsafe/out-of-range
values the same way form submission already does) — it is a new *input
source* for values that already flow through existing validated code paths,
not a new trust boundary.

## 9. Testing Strategy

Unchanged discipline from Version 2.5: every new behavior gets a real,
deterministic test (unittest, no live network) before being considered
done. Specifically:
- Fixture realism (2.6.2) needs regression tests confirming filters that
  were previously always-zero (`currency`, `walking_distance`,
  `public_transport_time`) now actually discriminate against the enriched
  demo data.
- The config loader (2.6.3) needs tests covering valid config, missing
  file, malformed JSON, and out-of-range values (mirroring
  `tests/web/test_forms.py`'s existing validation-test shape).
- The second fixture snapshot (2.6.4) needs a real acceptance-style test
  (mirroring `tests/acceptance/test_journey_c_saved_search_monitoring.py`)
  proving a genuine `price_decreased`/`availability_changed`/`new_match`
  event fires from two real monitoring runs — no synthetic
  `record_event()` shortcut.
- Saved-search validation (2.6.5) needs a test asserting a duplicate name
  is rejected or clearly warned, plus a regression test confirming
  existing saved searches with duplicate names (already in the real
  database from this pilot) don't break on read.

## 10. Backward-Compatibility Requirements

- No existing filter's behavior changes for **populated** data — only
  currently-`NULL` demo fixture fields gain real values, which is strictly
  additive (a filter that already worked correctly for RentCast data
  is unaffected).
- The config-file loader is an additional, optional way to populate the
  same values the form/CLI flags already accept — no existing CLI flag or
  form field is removed or renamed.
- Saved-search name validation must not break existing saved searches
  that already have duplicate names (the two `pilot-valencia-01` entries
  from this pilot session) — enforce uniqueness only at creation time,
  not retroactively.

## 11. Release Acceptance Criteria

- Full test suite passes (starting baseline: 1312 tests from v2.5.0-rc2).
- `scripts/health_check.py` 13/13 PASS, unchanged.
- A second pilot session (reusing `docs/38_Pilot_Feedback_Template.md`)
  completes with **zero** of the six Version 2.5 non-blocking findings
  still reproducing for any milestone actually shipped.
- No regression in any existing acceptance journey (`tests/acceptance/`).
- `docs/33_Release_Candidate_Acceptance.md`'s Known Gaps section is updated
  to reflect which gaps were closed vs. remain (accuracy, not silent
  deletion).

## 12. Risks and Mitigations

- **Risk**: Populating demo fixture `currency`/`property_type`/coordinates
  could make demo results look more "real" than they are, misleading a
  pilot user into thinking demo data is live commercial data.
  **Mitigation**: keep the platform name/address fields obviously
  fictional (already "Example City", `demo_platform`) and keep
  `RELEASE_NOTES`'s own honest labeling discipline — populate fields for
  functional realism, not to disguise the fixture's nature.
- **Risk**: Changing the `currency` filter to be more lenient (e.g.,
  "missing currency passes") could silently include a real apartment whose
  currency genuinely doesn't match, which is worse than the current
  fail-closed behavior for a real (non-demo) connector.
  **Mitigation**: do not change filter semantics at all this version —
  solve the problem by populating demo data instead (Milestone 2.6.2), so
  the existing, safer fail-closed behavior is preserved everywhere.
- **Risk**: A second monitoring fixture snapshot (2.6.4) could be
  over-engineered into a general "fixture versioning" system beyond what's
  needed.
  **Mitigation**: scope to exactly one additional snapshot with exactly
  the three documented change types (price, availability, new listing) —
  no configurable/parameterized fixture-diff system.
- **Risk**: Scope creep into the explicitly-out-of-scope items (real
  connectors, real routing, task queue/auth) given how closely related
  they are to the in-scope items.
  **Mitigation**: this document's Section 5 is the enforcement mechanism —
  any implementation PR touching those areas should be rejected or split
  into a future version's planning document.

## 13. Recommended Implementation Order

1. Milestone 2.6.1 (Pilot Materials Correctness) — smallest, safest, purely
   corrects already-shipped documentation/config, no code risk.
2. Milestone 2.6.5 (Saved-Search Name Validation) — small, isolated,
   low-risk, independent of the other milestones.
3. Milestone 2.6.2 (Demo Fixture Realism) — unlocks real testing for
   Milestone 2.6.4, so it must land first.
4. Milestone 2.6.4 (Monitoring Test Fixture Variation) — depends on 2.6.2's
   enriched fixture data existing.
5. Milestone 2.6.3 (Configuration Loading) — largest of the five, no
   dependency on the others, ordered last so earlier, smaller wins ship
   independently if this one needs more design discussion.

## Classification of the Nine Prioritized Evaluation Areas

| Area | Classification | Why |
|---|---|---|
| Real commercial rental-platform connectors | **Rejected** (for v2.6) | Blocked by each platform's ToS; no engineering decision unblocks this — needs an explicit legal/business approval this plan cannot grant. |
| Improved configuration loading | **Must have** | Directly closes a confirmed pilot finding (problem #2) — the platform's own shipped pilot materials assume a feature that doesn't exist. |
| Realistic pilot configuration | **Must have** | Directly closes confirmed pilot findings (problem #1) — the shipped example is actively misleading as written. |
| Currency-aware filtering | **Should have** | Real gap, but the *filter itself* is working as designed (fail-closed on missing data) — the fix is enriching demo data (Milestone 2.6.2), not changing filter logic (see Risks). |
| Travel-time and walking-distance support | **Later** | Literal transit-routing needs a real vendor/API decision (same category as already-open discovery/notification vendor decisions) — out of scope. Populating *coordinates* so the existing haversine calculator works is in scope (Milestone 2.6.2) and classified there, not here. |
| Monitoring against changing provider data | **Should have** | Real, valuable (Milestone 2.6.4), but depends on Milestone 2.6.2 landing first, and is a test-infrastructure improvement rather than a core-engine change. |
| Geographic-analysis presentation | **Must have** | Trivial, safe, fully diagnosed cosmetic fix (problem #5) with no architectural impact. |
| Saved-search name validation | **Should have** | Real, confirmed gap (problem #6), small and isolated, but not release-blocking on its own. |
| Provider reliability and observability | **Later** | Already reasonably built (Step 8's `ProviderHealth`/metrics); deeper dashboards/alerting are tied to the same open "real deployment target" decisions already logged in `notes/Questions.md`, not resolved by this plan. |

## Related Documents

- [33_Release_Candidate_Acceptance.md](33_Release_Candidate_Acceptance.md)
- [38_Pilot_Feedback_pilot-valencia-01_2026-07-17.md](38_Pilot_Feedback_pilot-valencia-01_2026-07-17.md)
- [40_Tag_Readiness_v2.5.0-rc2.md](40_Tag_Readiness_v2.5.0-rc2.md)
- [../MASTER_SPEC.md](../MASTER_SPEC.md) (Sections 44-46)
- [../notes/Questions.md](../notes/Questions.md)
