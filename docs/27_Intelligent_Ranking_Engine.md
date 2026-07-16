# 27 — Intelligent Ranking Engine V2

Version 2.5 Step 11. A modular, explainable, evidence-based decision engine that
transforms apartment ranking from a static weighted score into a system where every
apartment's final score comes with confidence, per-rule evidence, and a plain-
language explanation of why it ranked where it did.

## Why ranking is separated from analysis

The Analysis Engine answers "what is objectively true about this apartment" —
proximity scores, amenity evidence — with no notion of a searcher's preferences.
Ranking answers a different question: "given this searcher's priorities, which
apartments win." Separating them means the same computed evidence (analysis
composites, geo enrichments, knowledge rollups) serves any number of ranking
profiles without recomputation, and weights can change per search without touching
a single analyzer.

## Why scoring must remain explainable

An opaque score is unactionable — a renter can't trust it and a maintainer can't
debug it, and this project's own discipline (honest evidence, never fabricate, no
black boxes) already rules out an uninspectable model. Explainability is also what
makes weight-tuning possible at all: you can't correctly adjust "how much Price
should matter" if you can't see how much Price actually contributed last time.

## Which future modules contribute to ranking

Per the mission's own INPUTS list, every engine built since Step 4 is a candidate
evidence source: Dynamic Filters, Geographic Intelligence, Apartment History,
Knowledge Engine, Platform Reliability, Availability, Price History, Analysis
Results, Provider Health, Connector Reliability, Search History. A future engine
that produces structured, timestamped evidence adds one new `RankingRule` with zero
changes to `RankingEngineV2` itself.

## Why confidence matters

Evidence quality varies — a curated fact (confidence 1.0) versus an honest "no
evidence yet" default, or a geo estimate (0.4) versus an exact calculation (1.0).
Collapsing all of that into one final score without tracking confidence would let
weak or absent evidence silently masquerade as strong evidence. Confidence lets the
score honestly communicate how much to trust itself.

## Architecture

```
Apartment (already hard-filtered by v1 RankingEngine / FilterEngine)
        │
        ▼
RankingEngineV2.rank(apartments, context)
        │
        ▼
RankingPipeline.rank_one(apartment, context)  ── for every apartment
        │
        ├─► every RankingRuleRegistry rule .evaluate(apartment, context) → RankingEvidence
        │
        ├─► per-apartment weight renormalization (only among rules with real evidence)
        │
        ├─► RankingConfidence — weighted average of contributing rules' confidences
        │
        └─► RankingExplanation — top positive/negative factors, all_reasons
        │
        ▼
RankedApartmentV2 (final_score, confidence, contributions, explanation, warnings, computed_at)
        │
        ├─► RankingStatistics.compute_ranking_statistics() — coverage/average aggregates
        └─► report_generator.generate_report(ranking_v2_results=...) — rendered per listing
```

`RankingEngineV2` (`src/ranking_v2/engine.py`) is the outward-facing entry point:
apartments + a `RankingProfile` in, a fully explained, deterministically ordered
ranking out. It deliberately does not hard-filter apartments itself — that stays
the Dynamic Filter Engine's (or `search.criteria.apply_filters()`'s) job, already
done before this engine ever runs, the same "don't redesign an already-working
prior stage" reasoning already applied to the Filter Engine's and Geographic
Engine's own integration.

`RankingPipeline` (`src/ranking_v2/pipeline.py`) is the deterministic scoring core.
Rules run in registration order (the same fixed-order determinism `FilterEngine`
already guarantees), never mutating the `Apartment` they score.

## Rules

`RankingRule` (`src/ranking_v2/base_rule.py`) is the plugin contract: `evaluate(apartment,
context) -> RankingEvidence` and `metadata() -> RankingRuleMetadata`. Unlike
`BaseFilter`/`BaseAnalyzer`'s "thin contract with sensible defaults" shape, both
methods are abstract here — the four things a rule could plausibly do differently
(read a database, read optional context, compute from nothing) genuinely differ
enough per rule that no shared default would be right for most of them.

`RankingContext` (`src/ranking_v2/base_rule.py`) is the widest context object in
this codebase — one optional field per INPUT the mission names, all defaulting to
`None`/empty. A rule whose needed field is absent degrades to an honest "no
evidence" `RankingEvidence`, mirroring `FilterContext`/`AnalysisContext`/`GeoContext`'s
same reasoning applied to a much larger set of simultaneous inputs.

12 built-in rules, each named after (and reusing) a real, already-built engine:

| Rule (`rule_key`) | Reuses | Always has evidence? |
|---|---|---|
| `price` | `knowledge_service.average_city_price()` | Only once a search has run for this location |
| `price_trend` | `apartment_repository.get_price_history()` | Only with 2+ price observations |
| `walking_distance` | `GeoEnrichment.distances[WALKING]` | Only if `geo_engine` was supplied |
| `public_transport` | `GeoEnrichment.distances[PUBLIC_TRANSPORT]` | Only if `geo_engine` was supplied |
| `availability` | `Apartment.current_status` | **Always** |
| `lifestyle` | `GeoEnrichment.nearby` (confirmed categories only) | Only if `geo_engine` was supplied |
| `filter_preferences` | an already-run `FilterEngine`'s `FilterResult`s | Only if the caller supplies them |
| `analysis_composite` | `AnalysisResult.composite_scores` | Only if `analysis_results` has evidence |
| `platform_reliability` | `knowledge_service.platform_reliability()` | Only once observations accumulate |
| `connector_reliability` | `knowledge_service.connector_health()` | Only once observations accumulate |
| `provider_health` | `ProviderHealth.is_available_now` | Only if the caller supplies a health snapshot |
| `search_history` | a `SearchComparison` against the previous search | Only if the caller supplies one |

None recompute a formula another engine already owns — `price`/`price_trend`/
`platform_reliability`/`connector_reliability` call straight into the Knowledge
Engine and Apartment History's own read functions; `walking_distance`/
`public_transport`/`lifestyle` read the Geographic Engine's own `GeoEnrichment`
verbatim, including its own honestly-lower confidence for estimated travel times.

A future rule (e.g. once a real routing provider exists, or a new engine ships)
adds one new file implementing `RankingRule` and one `register_ranking_rule(...)`
call — `RankingEngineV2`/`RankingPipeline` require zero changes, proven directly by
`tests/ranking_v2/test_registry.py`'s `FutureRulePluginTests`.

## Weighting and renormalization — the honesty mechanism

`RankingWeights` (`src/ranking_v2/weights.py`) is a plain `rule_key -> weight` map.
Weights need not sum to 1 — the mission's own example ("Price 40%, Walking Distance
25%, ...") is accepted directly as `{"price": 40, "walking_distance": 25, ...}` and
normalized on read.

The key design decision: **a rule with no evidence for a given apartment is
excluded from both the score numerator and the weight-normalization denominator for
that specific apartment**, not counted as a zero. An apartment nobody computed a
`GeoEnrichment` for is never punished for missing "Walking Distance" evidence that
was never asked for in this run — its other, real evidence is reweighted to fill
the full 100%. This is what makes the engine "evidence-based" rather than
penalizing absent optional context as if it were bad news. Verified directly:
`tests/ranking_v2/test_pipeline.py::RenormalizationTests` proves a 50/50-weighted
profile where only one rule has evidence produces the *same* final score as a
100%-weighted profile on that one rule — not half of it.

## User Priorities

`RankingProfile` (`src/ranking_v2/profile.py`) is a named, reusable `RankingWeights`
preset. Two ship built in:

- **`DEFAULT_PROFILE`** — the mission's own worked example: Price 40%, Walking
  Distance 25%, Availability 15%, Public Transport 10%, Lifestyle 10%.
- **`COMPREHENSIVE_PROFILE`** — every registered rule weighted equally, surfacing
  every kind of evidence at once.

A caller is never limited to these two — `RankingProfile(name=..., weights=RankingWeights(...))`
builds any custom profile directly. `ui/cli.py` exposes `--use-ranking-v2` plus
`--ranking-profile {default,comprehensive}`.

## Explainability

`RankingExplanation` (`src/ranking_v2/models.py`) is built from each rule's own
`detail` sentence (written once, inside the rule, in the qualitative tone the
mission's own example uses — "Excellent walking distance," not
`walking_distance_score=0.91` — via a small shared `qualitative()` phrase-bucket
helper, `src/ranking_v2/rules/_phrasing.py`). Rules scoring `>= 0.6` become
candidate positive factors, `<= 0.4` become candidate negative factors, each sorted
by actual weighted contribution (not raw score) so the most decisive reasons come
first — matching the mission's own example ("Score 92.4 — Excellent walking
distance. Very reliable platform. Price below city average. ...").

## Confidence

`RankingConfidence` (`src/ranking_v2/models.py`) rolls up every contributing rule's
own confidence into one apartment-level number — a weighted average using the same
effective (renormalized) weights the score itself used, plus a `per_rule` map so
"why is confidence only 0.6?" is always answerable from the same object.

## Reports

`services/report_generator.py` gained one new, optional, default-`None`
`ranking_v2_results: list[RankedApartmentV2] | None` parameter (the same shape as
`analysis_results`/`geo_enrichments` — never persisted, only available in a report
generated in the same run that computed it). When present for a given apartment, the
report shows: final score, overall confidence, top positive factors, and top
negative factors. Omitted entirely (never a fabricated placeholder) when no
`ranking_engine_v2` was supplied — the same honesty convention every prior report
section already follows.

## Integration

`RentalResearchAgent` gained one new, optional, default-`None` `ranking_engine_v2`
parameter (byte-identical behavior for every existing caller, the same
`data_router`/`ai_router`/`filter_engine`/`geo_engine` precedent). It runs after v1's
own `RankingEngine.rank()` (which still does the actual hard-filtering and still
writes `search_results.rank`/`.score` completely unchanged) and re-scores the same
survivors with a real `RankingContext` (this run's own `conn`/`analysis_results`/
`geo_enrichments`). Its output is passed to `generate_report()` as an independent
artifact, never wired into `AnalysisEngine`'s or v1 `RankingEngine`'s own scoring —
the same "diagram vs. implementation reconciliation" reasoning already applied to
the Filter Engine's and Geographic Engine's own integration, made a third time.

`filter_results`/`provider_health`/`search_comparison` are intentionally **not**
auto-wired by `core/agent.py` in this sprint — those three rules remain real,
registered, and tested, available to any caller that builds its own `RankingContext`
directly, honestly dormant through the standard agent pipeline until a future
sprint wires them (the same "dormant rule" pattern the Dynamic Filter Engine
already established for fields that don't exist in the schema yet, applied here to
context that exists but isn't auto-assembled yet).

## Tests

94 new tests: unit tests for every new class (`RankingWeights`, `RankingProfile`,
`RankingRuleRegistry`, `RankingPipeline`, `RankingEngineV2`, `RankingStatistics`, the
shared models), all 12 rules' own behavior (real evidence and honest "no evidence"
paths), explainability tests (positive/negative factor selection and ordering),
weight tests (renormalization math, all-zero/empty edge cases), a plugin test
(a second, independent `RankingRule` registered at test time, resolved with zero
other code touched), performance tests (500 apartments × 12 real rules; 500
additional registered rules), agent-level integration tests (real Playwright-fixture
pipeline, mocked at the `BrowserCollector` boundary) proving the default path is
unaffected and the opt-in path runs correctly, and report-generator tests proving
real evidence renders and missing evidence is omitted. 734 tests total (640 existing
untouched + 94 new).
