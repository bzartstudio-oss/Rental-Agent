# 19 — Deep Analysis Engine

Status: **Live as of v2.0 Step 6 (2026-07-15)** — see `src/analysis/`.

Note on numbering: the mission for this sprint asked for `docs/18_Analysis_Engine.md`,
but `18` was already taken by [18_Connector_SDK.md](18_Connector_SDK.md) (v2.0 Step 5).
This is `19` instead — the same situation Step 5 hit with Search Memory, resolved the
same way: next free number, not a renumbering of anything existing.

This doc is the authoritative reference for the framework. `07_Analysis_Engine.md`
still owns the *pipeline position* (normalizer -> deduplicator -> change_detector ->
enricher -> engine.py) this system sits downstream of, and the original
per-sub-analyzer sketches (`distance.py`/`nearby.py`/`scores.py`) that this
implementation superseded with a registry-based plugin framework instead.

## Why the Analysis Engine Exists

A collected listing (title, price, address, images) tells a renter almost nothing
about what living there would actually be like — how far is it from things that
matter, what's nearby, how walkable is it. The Analysis Engine's job is to compute
that missing context *after* collection, from evidence that's actually available, and
attach it to the apartment without ever touching the apartment's own record. "Rich,
structured intelligence" (the mission's phrase) means: every score is traceable to
real evidence, every score's absence is honestly explained, and nothing is guessed.

## Why Analysis Is Separated From Data Collection

Two independent concerns, two independent failure modes. A connector's job is "did
this platform's listing get fetched and parsed correctly" — nothing about walking
distance or nearby amenities depends on which platform a listing came from, and
nothing about a connector's job depends on whether the Analysis Engine ever runs.
Keeping them separate means:

- A connector never needs geocoding/POI logic, keeping `src/connectors/sdk/`'s
  contract (build_url/parse/normalize/connector_info) exactly as narrow as v2.0 Step 5
  designed it.
- Analysis can be re-run, extended with a new analyzer, or have its scoring
  reconfigured *without* re-fetching anything — it operates entirely on already-stored
  `Apartment` rows and already-curated reference data.
- A broken analyzer can never corrupt listing data, because it's structurally
  incapable of writing to `apartments` — see "Immutability" below.

## Which Future Modules Will Use It

- `search/filters/proximity.py`/`score.py` (Dynamic Filter Engine, v2.0 Step 7 — not
  yet built) — `docs/04_Search_Request.md` "The Proximity/Score Dependency" already
  flagged that a `max_walking_minutes`/`location_score` filter needs the Analysis
  Engine to have computed that metric for a candidate apartment *in the same run*.
  This step is what makes that data exist; wiring filters to read it is Step 7's job.
- `ranking/` — not wired in this sprint (see "Deliberately Not Built"), but
  `apartment_analysis_metrics`/`AnalysisResult` are the eventual input for a
  location-aware ranking criterion, whenever that's requested.
- Any future analyzer needing another analyzer's output (e.g. a hypothetical
  "commute score" combining `walking_distance` and `public_transport`) — already
  possible today via `AnalysisContext.conn` and `storage.analysis_metrics_repository`,
  though no built-in analyzer does this yet (all eleven are independent).

## Why Every Analysis Result Must Be Reproducible

The same versioning promise every other v2.0 engine makes: a report or comparison must
mean the same thing whenever it's read, not silently shift as later runs change
things. `apartment_analysis_metrics` is append-only — nothing is ever `UPDATE`d — so a
past analysis stays exactly what it was when it was computed, comparable across
`docs/17_Search_Memory.md`-style run-over-run analysis later, and every score is
attributable to a specific `analyzer_version`/`source_module`, so a future formula
change is visible as new rows with a new version, not an unexplained score jump.

## Architecture

```
src/analysis/
  __init__.py
  models.py            # AnalysisContext, AnalyzerMetadata, AnalyzerResult,
                        #  CompositeScore, AnalysisResult
  base_analyzer.py       # BaseAnalyzer — the plugin contract
  registry.py              # AnalysisRegistry, register_analyzer decorator
  geo.py                     # pure haversine distance — the only "location math"
                              #  implemented for real this sprint
  scoring.py                   # CompositeScoreDefinition, ScoringConfiguration,
                                 #  compute_composite_scores, default_scoring_configuration
  pipeline.py                    # AnalysisPipeline — every analyzer, for one apartment
  engine.py                        # AnalysisEngine — every apartment, for one search
                                     #  (what core/agent.py holds)
  analysis_service.py                # record_analysis / latest_analysis / analysis_history
  analyzers/
    __init__.py                        # imports every analyzer -> self-registration
    walking_distance.py
    public_transport.py
    nearby_amenity.py                    # shared base + all 9 "nearby X" analyzers
```

**`AnalysisRepository` is `storage/analysis_metrics_repository.py`**, not a class
inside `src/analysis/` — same convention as every other v2.0 engine
(`ConnectorHealth` -> `knowledge.models`, "KnowledgeRepository" ->
`platform_intelligence_repository.py`): repositories live in `storage/`, engines/
services in their own package call them. `AnalysisEngine`/`AnalysisPipeline`/
`AnalysisService` map onto the mission's `AnalysisEngine`/`AnalysisPipeline`/
`AnalysisService` names directly; `AnalysisResult`/`AnalyzerResult`/`AnalyzerMetadata`
are in `models.py`; `AnalysisRegistry`/`BaseAnalyzer` are exactly as named.

## Immutability

`Apartment` (`storage/models.py`) is never imported for writing anywhere in
`src/analysis/` — every analyzer's `analyze()` signature takes an `Apartment` as a
read-only input and returns an `AnalyzerResult`; nothing in the package has a
reference to `apartment_repository.update_*`. Analysis output lives entirely in
`apartment_analysis_metrics`, a completely separate table. This is enforced by
convention (no analyzer imports write functions), not by a runtime guard — consistent
with how `analyzers/engine.py` similarly never mutates `RawListing` in place.

## Pipeline

```
core/agent.py, after Apartment History, before Ranking:

AnalysisEngine.analyze(conn, apartments, location, search_id)
  → one shared `computed_at` for the whole call
  → for each apartment:
      AnalysisPipeline.run(apartment, context)
        → for each analyzer in AnalysisRegistry.all():
            analyzer.analyze(apartment, context) -> AnalyzerResult
            (a raised exception is caught and turned into a score=None result
             with a warning — one broken analyzer never stops the others)
        → compute_composite_scores(analyzer_results, scoring_config) -> CompositeScore list
      → AnalysisResult(apartment_id, analyzer_results, composite_scores)
  → returns dict[apartment_id, AnalysisResult]

core/agent.py then:
  → analysis_service.record_analysis(conn, result) for each result (persists only
    metrics with a real score — see "Analysis History")
  → passes the dict directly to generate_report(..., analysis_results=...)
```

**Where this actually runs, vs. the mission's diagram.** The mission's own pipeline
diagram shows Analysis Engine *after* Search Memory and Knowledge Engine. Those two
systems' own established designs
([17_Search_Memory.md](17_Search_Memory.md)/[16_Knowledge_Engine.md](16_Knowledge_Engine.md)
"Where This Runs") require them to run at the very end of `RentalResearchAgent.run()`
— after ranking and report generation, since they need the final report path and
apartment counts. Moving them earlier would break that documented design and their
own passing tests, which "do not redesign completed modules unless absolutely
necessary" rules out. Analysis Engine instead runs as early as it correctly can:
right after Apartment History (once every apartment exists), before Ranking — matching
the mission's *relative* order between Analysis and Ranking exactly, while leaving
Search Memory/Knowledge Engine exactly where they've always been.

## Analyzer Lifecycle

Unlike `BaseConnector` (v2.0 Step 5), `BaseAnalyzer` is a thin contract, not a
multi-stage template method — an analyzer's whole job is one computation:

```python
class BaseAnalyzer(ABC):
    analyzer_name: str

    def metadata(self) -> AnalyzerMetadata: ...   # static self-description
    def analyze(self, apartment: Apartment, context: AnalysisContext) -> AnalyzerResult: ...
```

`AnalysisContext` carries what an analyzer needs beyond the apartment: `conn` (to read
curated reference data), `location` (the search's location string — same convention
Search Memory/Knowledge Engine already use), and one shared `computed_at` for the
whole run.

## How to Build a New Analyzer

1. Create `src/analysis/analyzers/<name>.py`.
2. Subclass `BaseAnalyzer`, set `analyzer_name = "<name>"`, decorate with
   `@register_analyzer`.
3. Implement `metadata()` (return an `AnalyzerMetadata`) and `analyze()`.
4. Add the module to the import list in `src/analysis/analyzers/__init__.py` — the
   only place that ever needs to change; `AnalysisPipeline`/`AnalysisEngine` do not.
5. If the new analyzer should feed a composite score, add it to
   `scoring.default_scoring_configuration()`'s relevant `CompositeScoreDefinition`
   (purely a weights-dictionary edit, not a code change to the scoring computation).
6. Write a test file covering: no-evidence path (returns `score=None` with a
   `warnings` entry), real-evidence path (returns a correct score), and metadata.

That's the entire list — no change to `AnalysisEngine`, `AnalysisPipeline`, or
`AnalysisRegistry` is ever required for a new analyzer.

## Evidence Model — Why Every Built-In Analyzer Is Dormant By Default

No connector populates `Apartment.latitude`/`.longitude` yet (confirmed dormant since
v2.0 Step 1), and no live geocoding/places/transit API has been chosen — that vendor
decision is explicitly still open
([07_Analysis_Engine.md](07_Analysis_Engine.md) "Open Questions"). Building real
geocoding integration now would mean inventing a data source decision this project has
deliberately deferred every time it's come up. Instead, every analyzer's evidence
comes from one of two real sources:

- **Real coordinate math** (`walking_distance`, `public_transport`): given two
  coordinate pairs, `src.analysis.geo.haversine_km` computes the actual great-circle
  distance — genuine arithmetic, not a placeholder. What's missing isn't the math,
  it's the coordinates: no connector provides them yet.
- **Curated reference facts** (the nine "nearby X" analyzers, plus the reference point
  `walking_distance`/`public_transport` need): `storage.reference_data_repository`
  (`knowledge_entries`, renamed from `knowledge_repository.py` in v2.0 Step 4.5) —
  hand-entered facts a human curates (e.g. "Example City has 4 known supermarkets"),
  not a live API call. Nothing seeds this automatically; every analyzer honestly
  reports "no evidence yet" until a real fact is curated for a given location.

This is the same "dormant until real data exists" pattern already established for
`platforms.connector_version`, `compare_coordinates`/`compare_presence` (v2.0 Step 2),
and "most common property types" (v2.0 Step 4) — verified against the real dev
database by seeding a few illustrative `Example City` facts (clearly fictional demo
data, consistent with `demo_platform`'s own reference-connector convention) and
confirming real, correctly-computed scores flow all the way through to the report.

## Scoring Model

Every analyzer returns a `score` in `[0, 1]` (or `None`) plus a `confidence` in
`[0, 1]` (or `None`, always paired with a `None` score). Composite scores
(`compute_composite_scores` in `scoring.py`) are a confidence-weighted average over a
named set of component analyzers:

```
contribution(analyzer) = analyzer.score * weight * (analyzer.confidence or 1.0)
composite.score = sum(contributions) / sum(effective_weights actually used)
```

A component with no evidence (`score=None`) is excluded from the average entirely —
never treated as `0`. A composite with *no* component having evidence is itself
`None`. "Overall Analysis Score" is the same computation one level up, averaging the
four named composites.

**Configurable, not hardcoded**: `ScoringConfiguration`/`CompositeScoreDefinition` are
plain data (a name plus an `analyzer_name -> weight` dict); `compute_composite_scores`
never references a specific analyzer or composite by name in its logic.
`default_scoring_configuration()` supplies a documented starting point — the four
composites and which analyzers feed each are a reasonable default, not the only valid
composition. `AnalysisEngine(scoring_config=...)` accepts any `ScoringConfiguration`,
same "generic logic + swappable config object" shape as `ranking/scoring.py`'s
weighted sum over `search/criteria.py`'s registered filters.

| Composite | Component analyzers (default weights) |
|---|---|
| Location Score | walking_distance (0.5), public_transport (0.3), nearby_parks (0.2) |
| Convenience Score | nearby_supermarkets (0.35), nearby_pharmacies (0.25), nearby_restaurants (0.25), nearby_parking (0.15) |
| Lifestyle Score | nearby_restaurants (0.4), nearby_gyms (0.35), nearby_parks (0.25) |
| Accessibility Score | walking_distance (0.25), public_transport (0.25), nearby_parking (0.2), nearby_hospitals (0.15), nearby_schools (0.1), nearby_universities (0.05) |
| Overall Analysis Score | location_score (0.3), convenience_score (0.25), lifestyle_score (0.2), accessibility_score (0.25) |

## Analysis History

Every `AnalysisEngine.analyze()` call produces a new set of `apartment_analysis_metrics`
rows (one per analyzer result *with* a real score, one per composite score) — never an
`UPDATE`. `analysis_service.latest_analysis()`/`analysis_history()` reconstruct
`AnalysisResult`-shaped data by grouping stored rows on their shared `computed_at`.

**One deliberate limitation**: a "no evidence" `AnalyzerResult` (`score=None`) is
*never persisted* — `metric_value` is `NOT NULL`, and there's nothing to store. This
means reconstructed history can show *what was scored*, but never *why something
wasn't* for a past run — only the in-memory `AnalysisResult` returned directly by
`AnalysisEngine.analyze()` in the *same* run carries `warnings` for missing evidence.
`core/agent.py` passes that same-run result straight to the Report Generator rather
than expecting it to re-derive warnings from the database, which is why "no evidence"
warnings show up in a freshly-generated report but wouldn't survive being re-derived
from a database read alone later.

## Report Integration

`services/report_generator.py::generate_report()` gained one new, optional,
default-`None` parameter: `analysis_results: dict[str, AnalysisResult] | None`. Every
existing caller (every test that doesn't pass it) gets byte-identical output to before
this sprint. When provided (the real path, via `core/agent.py`), each listing's HTML
block gains an analysis section showing: every individual analyzer's score (or `n/a`),
its confidence, its evidence summary, and — for analyzers with no evidence — a visible
warning; plus every composite score, including "Overall Analysis Score."

## Plugin System

`AnalysisRegistry` mirrors `src.connectors.sdk.ConnectorRegistry` (v2.0 Step 5)'s
self-registration idea but is deliberately simpler: connectors are lazily imported
per-platform on demand (`ConnectorFactory.get()` doesn't know which platform it needs
until called); every registered analyzer runs for *every* apartment, so there's no
"which one do I need this time" question to defer. `src/analysis/analyzers/__init__.py`
eagerly imports every built-in analyzer module once, which is the only "loading" this
registry needs — no lazy `importlib` resolution, no naming convention to reverse-engineer.

## Deliberately Not Built (Out of Scope for v2.0 Step 6)

- **No real geocoding, places, or transit API integration.** Every analyzer's evidence
  is either pure coordinate math or curated reference data — see "Evidence Model."
  Picking a real vendor is a deferred product decision, unchanged by this sprint.
- **No wiring into `search/criteria.py`/ranking.** `docs/04_Search_Request.md`'s
  proximity/score filters and any location-aware ranking criterion are the Dynamic
  Filter Engine's job (v2.0 Step 7, not yet built) — this sprint only makes the
  underlying metrics exist.
- **No machine learning, no AI, no predictive inference anywhere** — every score is
  either deterministic arithmetic (haversine) or a direct, documented function of a
  curated fact (amenity count / saturation constant). Nothing is trained, fitted, or
  inferred.

## Related

- [07_Analysis_Engine.md](07_Analysis_Engine.md) — the original pipeline-position doc
  and the design this implementation superseded
- [03_Data_Model.md](03_Data_Model.md) — `apartment_analysis_metrics` schema
- [16_Knowledge_Engine.md](16_Knowledge_Engine.md) / [17_Search_Memory.md](17_Search_Memory.md) —
  "Where This Runs" sections that constrain this sprint's pipeline placement
- [18_Connector_SDK.md](18_Connector_SDK.md) — the plugin/registry pattern this
  package's `AnalysisRegistry` deliberately simplifies
- [10_Roadmap.md](10_Roadmap.md) — "Version 2.0" Step 6 for the full implementation summary
