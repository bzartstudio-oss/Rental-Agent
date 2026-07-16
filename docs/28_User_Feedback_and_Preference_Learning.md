# 28 — User Feedback and Preference Learning Engine

Version 2.5 Step 12. A modular system that learns user preferences from explicit,
traceable evidence — deterministic, no machine learning, no opaque prediction.
Application code remains fully deterministic; learning happens through stored user
actions, preference observations, and reproducible calculations.

## Why user preference learning is separate from the Knowledge Engine

The Knowledge Engine (`src/knowledge/`) observes objective, system-side facts —
platform reliability, connector health, response times — with no notion of any
individual person. This engine observes one specific user's actions to infer what
*that person* values. Different subjects (platform behavior vs. individual taste),
different lifecycles (Knowledge Engine rollups aggregate across everyone forever;
preference profiles are per-`profile_id` and must stay editable/resettable by that
person alone). Conflating them would let one person's taste signals pollute
system-wide platform stats, or vice versa — a genuine separation-of-concerns
violation, not just a naming convenience.

## Why explicit feedback is more trustworthy than inferred behavior

Explicit feedback (a manual rating, a manual weight change, a directly-set
preference, a filter choice) states intent with no interpretation gap. Inferred
behavior (e.g. "saved 3 apartments with short walks") is a pattern in noisy real
action that could have many explanations — a hypothesis, not a fact. This is
implemented concretely in `src/feedback/decay.py`: every explicit observation is
weighted `explicit_weight_multiplier` (default `3.0`) times an inferred one of the
same magnitude, and explicit *settings* (passed directly to
`build_preference_profile(explicit_settings=...)`) bypass inference entirely —
"Explicit user profile settings always take precedence over inferred preferences"
is not a policy statement, it's a code path.

## How preference learning influences ranking without making it opaque

`src/feedback/ranking_adapter.py` is the *only* module that imports both
`feedback` and `ranking_v2` — `FeedbackEngine` never touches an individual
`RankingRule`, and `RankingEngineV2` has zero awareness `feedback` exists. The
adapter only ever produces a *suggested* `RankingProfile`; the user's own explicit
profile remains authoritative unless `FeedbackMode.ASSISTED` is chosen, and even
then the suggestion is built from the same `RankingEvidence`/confidence shapes
Ranking V2 already established (`docs/27_Intelligent_Ranking_Engine.md`) — every
suggested weight traces back to a specific, inspectable `PreferenceValue` with its
own confidence and evidence count, never a black-box number.

## How preference changes remain reversible and auditable

Two append-only tables, never one mutable one: `feedback_events` (migration 0007)
records every raw action, `preference_adjustments` records every time a
preference's *computed* value/confidence actually changed, with why. Neither table
has an `update_*`/`delete_*` function anywhere in `storage/feedback_repository.py`
— the only way to "change" history is to add a new row. `undo_preference_adjustment()`
writes a new row reversing a prior one; `reset_inferred_preferences()` writes new
"reset" rows that move the evidence cutoff forward without touching a single raw
event. See "Preference Calculation" below for exactly how this makes undo/reset
genuinely effective rather than immediately overwritten by the next rebuild.

## Which information must never be inferred without user confirmation

Any sensitive personal characteristic — gender, ethnicity, religion, health
status, sexual orientation, political views, or similar — is never inferred from
browsing or rental behavior, full stop. Enforced structurally, not just
documented: `tests/feedback/test_privacy.py` asserts every one of the 23
registered preference dimensions' `preference_key` and `metadata().description`
contain no sensitive-trait terminology, and that every rule's `metadata().category`
is a real-estate concept (cost, location, listing, amenity, logistics, trust) —
never a category implying personal identity. Personal constraints (e.g.
accessibility needs) are only ever stored when a user explicitly provides them for
the search itself — no rule here infers one from indirect behavior.

## Architecture

```
FeedbackEvent (append-only)
        │
        ▼
FeedbackEngine.record_event()
        │
        ├─► FeedbackRegistry.rules_for_event_type() ──► every relevant PreferenceRule.observe()
        │                                                      │
        │                                                      ▼
        │                                          PreferenceObservation (persisted, append-only)
        │
        ▼
FeedbackEngine.build_preference_profile()
        │
        ├─► for each of 23 registered rules: rule.aggregate(observations since last reset/undo)
        │
        ├─► PreferenceAdjustment written only if the computed value actually changed
        │
        └─► PreferenceSnapshot persisted (a versioned, full-profile serialization)
        │
        ▼
PreferenceProfile (per-preference: current_value, PreferenceConfidence, source_types,
                    last_updated, explanation, history)
        │
        ├─► feedback.ranking_adapter.resolve_ranking_profile() ──► suggested/applied RankingProfile
        └─► report_generator.generate_report(preference_profile=...) ──► rendered per report
```

`FeedbackEngine` (`src/feedback/engine.py`) is the orchestrator implementing every
auditability method the mission requires. `FeedbackService`
(`src/feedback/service.py`) is thin read/write orchestration over
`storage/feedback_repository.py`, mirroring `knowledge_service.py`'s own shape —
deciding *when*/*what*/*why* to record stays `FeedbackEngine`'s job.

## Event Lifecycle

`FeedbackEventType` (`src/feedback/event_types.py`) provides the 15 named
constants the mission requires (`VIEWED`, `SAVED`, `SHORTLISTED`, `REJECTED`,
`CONTACTED`, `IGNORED`, `MANUAL_RATING`, `MANUAL_RANKING_UP`,
`MANUAL_RANKING_DOWN`, `FILTER_SELECTED`, `FILTER_REMOVED`, `WEIGHT_CHANGED`,
`SEARCH_REPEATED`, `RESULT_OPENED`, `ORIGINAL_LISTING_OPENED`) — a plain class of
string constants, not a `str, Enum` restricting `FeedbackEvent.event_type`'s
actual field type. "Future event types must be addable without changing
FeedbackEngine" (the mission's own words) means a future event type is just a new
string passed to `record_event()`; nothing anywhere validates `event_type` against
`KNOWN_EVENT_TYPES`, the same "open-ended by convention" reasoning
`geography.nearby_search.NEARBY_CATEGORIES` already established.

Every event carries: `event_id` (a real UUID, generated at construction),
`profile_id`, `search_id`, `apartment_id`, `event_type`, `event_value` (a flexible
dict — a rating, a filter key/value, a weight delta), `occurred_at`, `source`,
`session_id`, `metadata`, `ranking_profile` (a snapshot of the active
`RankingProfile` at the time), and `search_filters` (a snapshot of the active
criteria) — every field the mission's STORE section requires.

## Preference Calculation

`PreferenceRule` (`src/feedback/base_rule.py`) is the plugin contract. Four
shared intermediate base classes (`ImportancePreferenceRule`/
`ThresholdPreferenceRule`/`CategoricalPreferenceRule`/`BooleanPreferenceRule`)
each provide one real, shared `aggregate()` implementation — the mission's own
"Learning Rules" section describes ONE consistent algorithm, so a concrete rule
only ever implements `observe()` (the one thing that genuinely differs per
preference dimension), mirroring the `DormantBooleanFilter`/`DormantStringFilter`
shared-base pattern `filter_engine/filters/dormant_base.py` already established,
generalized from "share validation" to "share the entire aggregation algorithm."

23 built-in rules, split honestly into two groups:

- **12 real, apartment-field-backed dimensions** (`price_sensitivity`,
  `maximum_budget`, `walking_distance`, `public_transport`,
  `availability_importance`, `property_type`, `minimum_area`, `number_of_rooms`,
  `platform`, `neighborhood`, `lifestyle`, `nearby_services`) — correlate real
  `Apartment`/`GeoEnrichment` fields against `SAVED`/`REJECTED`/etc. outcomes.
- **11 dormant-field dimensions** (`room_type`, `private_bathroom`,
  `private_kitchen`, `air_conditioning`, `furnished`, `pets_allowed`, `balcony`,
  `parking`, `utilities_included`, `internet_included`, `number_of_flatmates`) —
  the identical "no structured schema field exists" situation
  `filter_engine/filters/amenities.py`'s 27 dormant filters already documented
  for the same fields (v2.5 Step 9). A saved/rejected apartment can never be
  checked for "does it actually have a balcony," so these rules honestly learn
  only from **explicit filter selections/removals** — real, structured evidence
  of intent, even though it can never be corroborated against a listing outcome.
  Each `preference_key` matches the identical `key` string
  `filter_engine.filters.amenities`/`preferences_and_other` already uses for the
  same concept.

**Renormalization/decay is centralized, not reimplemented per rule** —
`src/feedback/decay.py`'s `compute_confidence()`/`decayed_weight()` are the one
place age-decay, explicit-outweighs-inferred, and conflict-reduces-confidence math
lives; every `aggregate()` implementation calls into it.

## Confidence Model

`PreferenceConfidence.overall = consistency * volume`:

- **`consistency`** (`0` fully conflicting to `1` fully one-directional) —
  "conflicting behavior must reduce confidence" (the mission's own words).
- **`volume`** (saturating as more decayed-weighted evidence accumulates, default
  saturation at `5.0` total weight) — "a single action must not strongly alter
  the profile." A single inferred observation (weight ≤ 1.0) yields confidence
  ≤ 0.2; a single explicit one (weight ≤ 3.0 with the default multiplier) yields
  confidence ≤ 0.6 — meaningfully more trusted, but never treated as certain.

`DecayConfig` (`half_life_days=30.0`, `explicit_weight_multiplier=3.0`,
`saturation_weight=5.0`) is a real, overridable dataclass passed to
`FeedbackEngine(decay_config=...)` — "the decay rule must be configurable" (the
mission's own words) is a constructor parameter, not a hidden module constant.

## Explicit versus Inferred

Two distinct mechanisms, both real:

1. **Explicit *settings*** — passed directly to
   `build_preference_profile(explicit_settings={"property_type": {"preferred": "house"}})`
   — bypass rule aggregation entirely, confidence `1.0`, `is_explicit=True`.
   Always authoritative, exactly the mission's "Explicit user profile settings
   always take precedence."
2. **Explicit *observations*** — e.g. a `FILTER_SELECTED` event — still go
   through the same shared `aggregate()` math as inferred ones, just weighted
   `explicit_weight_multiplier`× more heavily. This is "explicit events count
   more strongly," a real but not absolute precedence, distinct from (1)'s
   absolute override.

## Auditability

Every method the mission's AUDITABILITY section names is implemented on
`FeedbackEngine`: `record_event()`, `build_preference_profile()`,
`get_preference_history()`, `explain_preference()`,
`undo_preference_adjustment()`, `reset_inferred_preferences()`,
`export_feedback_history()`, `compare_preference_profiles()`.

**The adjustment log is the source of truth for "current" values, not a
recomputed-every-time aggregate.** `build_preference_profile()` computes what the
aggregate *would* be from persisted observations (respecting any reset/undo
cutoff) and only writes a new `PreferenceAdjustment` row when that differs from
the last one on file. This is what makes undo/reset genuinely effective: both
write a new adjustment whose `applied_at` becomes the new evidence cutoff
(`FeedbackEngine._effective_cutoff()`), so only *future* events can out-vote a
manual undo/reset — otherwise the very next rebuild would silently re-derive the
same value from the still-present (and correctly still-present) historical
observations, erasing the undo/reset's effect.

`reset_inferred_preferences()` never touches a preference whose latest adjustment
is `"explicit"` — only preferences that are currently inferred get reset to
neutral (`current_value=None`, `confidence=0.0`). No `FeedbackEvent`/
`PreferenceObservation` row is ever deleted by either operation.

## Ranking Integration

`src/feedback/ranking_adapter.py`. Three modes (`FeedbackMode`):

- **`EXPLICIT_ONLY`** — `resolve_ranking_profile()` returns the caller's own
  `RankingProfile` completely unchanged (identity-equal).
- **`SUGGESTED`** (the default) — behaves identically to `EXPLICIT_ONLY` for
  what actually ranks anything; `suggest_ranking_profile()` is still callable
  separately for display, it simply never becomes authoritative.
- **`ASSISTED`** — returns a new `RankingProfile`, seeded from the caller's own
  explicit weights (`base_weights=explicit_ranking_profile.weights`) and
  overridden only for the (currently 5) preference dimensions with a
  `ranking_v2` rule_key counterpart (`price_sensitivity`→`price`,
  `walking_distance`, `public_transport`, `availability_importance`→`availability`,
  `lifestyle`) — and only when confidence clears `0.4` (explicit preferences
  bypass this threshold). The other 18 preferences don't yet have a matching
  ranking rule to suggest a weight for — an honest, documented limitation, the
  same "future modules" reasoning `docs/27`'s own "Which future modules will
  depend on this engine" section already used.

## Filter Engine Integration

`src/feedback/filter_integration.py`. `record_filter_selection_events()`/
`record_filter_change_events()` record one `FILTER_SELECTED`/`FILTER_REMOVED`
event per active/changed criterion — purely observational. Neither function ever
mutates the criteria dict passed to it, and neither reads back into
`SearchRequest.criteria`/`FilterEngine`'s own hard-filter behavior — "Required
conditions must remain explicit user decisions" (the mission's own words) is
enforced by this module simply never having a code path that could change one.

## Integration (Agent/Report/CLI)

`RentalResearchAgent` gained three new, optional, default-`None`/`SUGGESTED`
parameters: `feedback_engine`, `feedback_profile_id`, `feedback_mode` — every
existing caller is completely unaffected. When supplied, every active search
criterion is recorded as feedback (linked to `search_id`), and — when
`ranking_engine_v2` is also supplied — that run's `RankingProfile` is resolved
through `resolve_ranking_profile()` before ranking runs.

`services/report_generator.py` gained one new, optional, default-`None`
`preference_profile` parameter, rendering explicit preferences separately from
inferred ones (each with its own confidence) — a reader can see directly which
preferences would disappear under `EXPLICIT_ONLY` mode without the report
needing to re-run ranking a second time to prove it.

`src/ui/feedback_cli.py` — a second, thin entry point (kept separate from
`ui/cli.py`'s search command, preserving its own backward compatibility) with
`record`/`profile`/`explain`/`history`/`undo`/`reset`/`export` subcommands.

## Database

Migration `0007_feedback_and_preferences.sql` — four new tables, `0001`–`0006`
untouched: `feedback_events`, `preference_observations`, `preference_adjustments`,
`preference_snapshots`. Indexes chosen for the mission's own named query patterns:
`(profile_id, occurred_at)`, `(apartment_id, event_type)`, `(search_id, occurred_at)`
on `feedback_events`; `(profile_id, preference_key)` on both
`preference_observations` and `preference_adjustments`. No `update_*`/`delete_*`
function exists anywhere in `storage/feedback_repository.py` for
`feedback_events` — verified directly in `tests/feedback/test_repository.py`.

## Privacy and Safety

See "Which information must never be inferred" above for the guarantee itself.
**Retention**: nothing here ever deletes a `FeedbackEvent` — retention/deletion
policy (e.g. a data-subject deletion request) is explicitly out of this sprint's
scope, the same "framework, not every downstream policy" reasoning prior steps
have applied; a real deletion feature would need its own design pass on top of
this append-only foundation, not bolted on silently. **Reset**: covered above —
`reset_inferred_preferences()` never deletes anything, only moves the evidence
cutoff forward for future rebuilds.

## How to add a new feedback event type

Nothing to register. Construct `FeedbackEvent(event_type="your_new_type", ...)`
and call `record_event()` — any `PreferenceRule` whose `relevant_event_types()`
includes that string will observe it automatically via
`FeedbackRegistry.rules_for_event_type()`.

## How to add a new preference dimension

1. Pick the shared base that matches your value shape: `ImportancePreferenceRule`
   (`{"importance": float}`), `ThresholdPreferenceRule` (`{"preferred": float}`),
   `CategoricalPreferenceRule` (`{"preferred": str, "distribution": dict}`), or
   `BooleanPreferenceRule` (`{"wants": bool, "strength": float}`).
2. Implement `relevant_event_types()`, `observe()`, and `metadata()` — `aggregate()`
   is already provided.
3. Call `register_preference_rule(YourRule())` at module import time (see any file
   under `src/feedback/rules/` for the pattern), and add the module to
   `src/feedback/rules/__init__.py`'s eager-import list.
4. If the new preference maps to a `ranking_v2` rule_key, add one entry to
   `ranking_adapter._PREFERENCE_TO_RANKING_RULE`.

`FeedbackEngine`/`FeedbackRegistry` require zero other changes — proven directly
by `tests/feedback/test_registry.py`'s `FuturePreferenceRulePluginTests`.

## Tests

130 new tests: unit tests for every new class (`DecayConfig`/confidence math,
`FeedbackRegistry`, the 4 shared `aggregate()` implementations, `FeedbackEngine`'s
8 auditability methods, the ranking adapter's 3 modes, filter integration), all 23
rules' own `observe()` behavior (real evidence and honest no-evidence paths),
migration + append-only-history tests (no `update_*`/`delete_*` function exists),
conflicting-feedback/confidence tests (repeated consistent events strengthen
confidence, conflicting events reduce it, a single event never creates an extreme
preference), explicit-precedence tests, reset/undo tests (raw events survive,
explicit preferences untouched), reproducibility tests (rebuilding from unchanged
history at the same reference time is byte-identical), a plugin test (a second,
independent `PreferenceRule` registered at test time, resolved with zero other
code touched), performance tests (500 events against all 23 real rules), a
structural privacy guardrail test (every registered preference key/description/
category checked against a sensitive-terminology blocklist), agent-level
integration tests (real Playwright-fixture pipeline, mocked at the
`BrowserCollector` boundary) proving the default path is unaffected, and CLI
tests. 864 tests total (734 existing untouched + 130 new).
