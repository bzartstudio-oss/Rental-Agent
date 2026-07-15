# 26 — Geographic Intelligence Engine

Version 2.5 Step 10. A modular, provider-independent engine that calculates spatial
relationships between apartments and points of interest — distances, estimated travel
times, and nearby-service counts — and hands the result to the report generator as an
independent artifact, never mutating the `Apartment` it describes.

## Why this isn't a map viewer

A map viewer renders a picture. This engine answers a different question: *given two
points, what is the relationship between them, and how confident are we in that
answer?* Nothing here draws a map or embeds a map widget — every output is structured
data (`GeoResult`/`NearbyPlace`/`GeoEnrichment`), consumed by the report generator the
same way `AnalysisResult` already is. Calling it "Geographic Intelligence" rather than
"Maps" is deliberate: a map is one possible *rendering* of the underlying spatial
facts this engine computes; this sprint builds the facts, not the picture.

## Why map providers must be replaceable

No real routing/geocoding/places API is integrated in this sprint — not because one
couldn't be, but because picking one (Google Maps, Mapbox, OSM Overpass, HERE, ...) is
a real vendor/cost/rate-limit decision this sprint deliberately doesn't make, the same
reasoning that has already deferred a real data provider decision twice before (the
Analysis Engine's own "no geocoding/places/transit API," `docs/19_Analysis_Engine.md`
"Deliberately Not Built"; the Connector SDK's `sample_json_feed` validation exercise,
`docs/22_SDK_Validation_Sprint.md`). If the engine were hardcoded against one vendor's
SDK, adopting a different provider later — or supporting several simultaneously,
falling back when one is unavailable — would mean rewriting the engine itself. Instead,
every provider (today's `HaversineGeoProvider`, and any future real routing/places
provider) implements one interface, `GeoProvider`, and self-registers into
`GeoProviderRegistry` at import time. `GeographicEngine`, `DistanceCalculator`, and
`NearbySearch` never import a specific provider class — they resolve one through
`GeoProviderFactory`, exactly mirroring how `ConnectorFactory`/`ProviderFactory`/
`FilterFactory` already keep their own domains provider-agnostic.

## Which future modules will depend on this engine

- **The Ranking Engine** (`ranking/ranking_engine.py`) — a location-quality signal
  (walking time to the city center, real nearby-service coverage) is an obvious
  ranking input, once a real routing/places provider makes those numbers trustworthy
  enough to weight, not just display.
- **The Dynamic Filter Engine** (`src/filter_engine/`) — several already-built dormant
  filters (`maximum_distance`, `walking_distance`, `public_transport_time`, the
  `nearby_amenity`-style filters) are exactly the shape this engine could eventually
  feed real evidence into, once its own reference-point/curated-data prerequisites are
  met for a given location.
- **A future comparison/recommendation feature** — "show me apartments within 20
  minutes of my office" is a real product feature this engine's `GeoContext`/
  `DistanceCalculator` shape already supports; building it is out of this sprint's
  scope.

None of these are wired up in this sprint — see "Integration" below for why the
engine's output is deliberately kept independent rather than threaded into any of
them yet.

## How geographic calculations improve ranking (today and later)

Today: not directly — see "Integration" below for why this sprint's output is passed
to the report generator as an independent artifact (mirroring `analysis_results`/
`ai_summary`), not wired into `RankingEngine.rank()`'s own scoring. The value today is
informational: a renter can *see* a real (if honestly estimated) walking time and
nearby-amenity summary next to each ranked result. Later, once a production geo
provider exists, the same `GeoResult`/`NearbyPlace` shapes this sprint defines could
feed a new ranking factor without any change to this engine — the numbers it already
produces (distance, confidence) are exactly what a scoring formula would need.

## Architecture

```
Apartment (latitude/longitude, never modified)
        │
        ▼
GeographicEngine.enrich(apartment, context)
        │
        ├─► DistanceCalculator ──► GeoProviderFactory ──► GeoProvider (haversine, ...)
        │         │                                              │
        │         └────────────── GeoCache (optional) ◄──────────┘
        │
        └─► NearbySearch ──► GeoProviderFactory ──► GeoProvider.find_nearby()
                  │
                  └────────── GeoCache (optional)

        ▼
GeoEnrichment (apartment_id, distances: {TravelMode: GeoResult}, nearby: {category: [NearbyPlace]})
        │
        ├─► GeoStatistics.compute_geo_statistics() — coverage/confidence aggregates
        ├─► GeoHistory.record_geo_enrichment() — geo_enrichment_history (migration 0006)
        └─► report_generator.generate_report(geo_enrichments=...) — rendered per listing
```

`GeographicEngine` (`src/geography/engine.py`) is the single orchestrator: it never
constructs a connector, never touches `AnalysisEngine`/`RankingEngine`, and its only
job is turning `(apartment, context)` into a `GeoEnrichment` — the same single-
responsibility discipline every prior v2.0/v2.5 engine (`AnalysisEngine`,
`FilterEngine`) already keeps.

An apartment with no `latitude`/`longitude` — true for every listing scraped through
the demo/HTML connector today, since no connector populates coordinates for that
platform — gets an honestly empty `GeoEnrichment` (no distances, no fabricated
evidence), the same "no evidence" convention `walking_distance.py`/`nearby_amenity.py`
already established for the identical two missing facts (coordinates, a curated
reference point).

## Providers

`GeoProvider` (`src/geography/base_provider.py`) is the plugin contract: `is_available()`,
`metadata()`, `calculate_distance(origin, destination, mode, context)`,
`find_nearby(origin, category, context)`. Every method that touches the database
receives a `GeoContext` (`conn`, `location`) — mirroring `FilterContext`/
`AnalysisContext` — so a curated-data provider can read `knowledge_entries` while a
future real routing-API provider simply ignores both fields and makes its own HTTP call.

### HaversineGeoProvider — the one built-in provider

Registered as `"haversine"`. Two genuinely different kinds of evidence, both honest
about what they are:

- **Straight-line distance** — exact arithmetic (`src.analysis.geo.haversine_km`,
  reused, not reimplemented — the same great-circle math `walking_distance.py`/
  `public_transport.py` already use). Confidence `1.0`.
- **Walking/cycling/driving/public-transport travel time** — straight-line distance
  divided by a documented, tunable average speed per mode (walking 5 km/h, cycling
  15 km/h, driving 30 km/h, public transport 20 km/h — real-world rough averages, not
  fabricated numbers). This deliberately ignores actual roads, terrain, and traffic —
  it is not real routing, and is never presented as such. Confidence `0.4`, honestly
  lower than the exact distance calculation, reflecting that it's an estimate.
- **Nearby search** — reuses the exact `nearby_amenities`/`f"{location}:{category}"`
  `knowledge_entries` convention `analysis/analyzers/nearby_amenity.py` already
  established, extended from that analyzer's 9 categories to all 17 the mission
  names. When no curated fact exists, `find_nearby()` returns one `NearbyPlace` with
  `count=None`/`confidence=None` and a warning (mirroring `nearby_amenity.py`'s own
  "No curated {type} data for {location!r} yet" message) — an honest "no evidence"
  result, not a silently empty list (which couldn't carry the mission-mandated
  provider/calculation-method/timestamp fields).

A future provider (Google Places/Maps, Mapbox, OSM Overpass, a transit API, ...) adds
one new file implementing `GeoProvider` and one `register_geo_provider(...)` call —
`GeographicEngine`, `GeoProviderFactory`, `DistanceCalculator`, and `NearbySearch`
require zero changes, proven directly by `tests/geography/test_registry.py`'s
`FutureProviderPluginTests`, which registers a second, independent provider at test
time and resolves it by id with no other code touched.

## Caching

`GeoCache` (`src/geography/cache.py`) is the first real caching infrastructure this
codebase has — the Production Readiness Review (`docs/23_Production_Readiness_Review.md`,
Question 4) found "zero caching infrastructure exists anywhere in this codebase";
this is the first real answer. A plain, generic `key → value` TTL store (any value
type, not geo-specific), so `DistanceCalculator`/`NearbySearch` share one cache
instance without either reimplementing expiry logic. `GeoCache.make_key(*parts)`
builds a stable, human-readable key from any number of parts. `set(key, value,
ttl_seconds=None)` uses the cache's own default TTL unless overridden per entry;
`invalidate(key)`/`clear()` give the "configurable invalidation" the mission asks for
beyond just TTL expiry. Caching is entirely optional — every calculator accepts
`cache: GeoCache | None = None`, defaulting to no caching, so nothing forces every
caller to manage cache lifetime.

## Routing

`DistanceCalculator` is the one place that actually resolves a provider and
(optionally) touches the cache; `TravelTimeCalculator` and `RouteCalculator` both
delegate to it rather than duplicating provider-resolution or caching logic.
`RouteCalculator.calculate_route()` builds a `Route` — honestly always exactly one
segment today, since no real routing API is integrated (the mission's own "Do not
hardcode any map provider" constraint) — never a fabricated multi-waypoint path. A
future provider capable of real multi-segment routing fits the same `Route`/
`RouteSegment` shape without any change to `RouteCalculator`'s public interface.

## Nearby Search

`NearbySearch` (`src/geography/nearby_search.py`) resolves a provider through
`GeoProviderFactory` (identical caching/resolution pattern to `DistanceCalculator`)
and exposes `find_nearby(origin, category, context)` plus
`find_nearby_all_categories(origin, context)` for the full 17-category sweep. The 17
categories (`NEARBY_CATEGORIES`) are a plain tuple of strings, not an enum — a future
category never requires a code change here, only a provider that recognizes it, the
same "open-ended by convention" shape `ConnectorMetadata.extra_capabilities` already
uses for the identical reason.

## Every result's mandated fields

The mission requires every result to carry distance, travel time, confidence,
timestamp, provider, and calculation method. `GeoResult` and `NearbyPlace`
(`src/geography/models.py`) both carry every one of these — a field that doesn't
apply (e.g. `travel_time_minutes` for a `STRAIGHT_LINE` result, `distance_km` for a
curated-count-based `NearbyPlace`) is honestly `None`, never omitted from the shape
itself.

## Integration

```
Apartment ↓ Geographic Engine ↓ Analysis Engine ↓ Knowledge Engine ↓ Ranking Engine ↓ HTML Report
```

is the mission's own diagram. As built, `GeographicEngine` runs *after* the Analysis
Engine (not before it) and its output is handed directly to the report generator as
an independent artifact — never threaded into `AnalysisEngine`'s or
`RankingEngine.rank()`'s own scoring. This is the same "diagram vs. implementation
reconciliation" already made explicitly twice before: the Deep Analysis Engine
(v2.0 Step 6) and the Dynamic Filter Engine (v2.5 Step 9) both placed their own
diagram-implied step earlier than where it's actually safe/correct to run, for the
same reason — wiring a brand-new engine's output directly into an already-tested
prior step's scoring logic risks destabilizing code that already works and is already
covered by its own test suite, for no benefit this sprint's mission actually asks for
(the mission's own "REPORTS must display" section only asks for *display*, not a
ranking change). `RentalResearchAgent` gained one new, optional, default-`None`
`geo_engine` parameter (byte-identical behavior for every existing caller, the exact
`data_router`/`ai_router`/`filter_engine` precedent), wired in right after the
(optional) Filter Engine step and before `RankingEngine.rank()`; its output
(`dict[str, GeoEnrichment]`) is passed straight to `generate_report()` alongside
`analysis_results`/`ai_summary`. `ui/cli.py` gained one new, off-by-default
`--use-geo-engine` flag.

`GeoHistory` (`src/geography/history.py`) records one `geo_enrichment_history` row
(migration `0006_geo_enrichment_history.sql`) per apartment per run — `provider_id`/
`calculation_method` are read from the `GeoEnrichment`'s own results (recorded as
`"mixed"` when different travel modes genuinely used different calculation methods,
`"unknown"` when the enrichment carries no distances at all), never hardcoded by the
calling code, preserving the engine's provider-independence guarantee all the way to
the history table.

## Reports

`services/report_generator.py` gained one new, optional, default-`None`
`geo_enrichments: dict[str, GeoEnrichment] | None` parameter (the same shape as
`analysis_results`/`ai_summary` — never persisted, only available in a report
generated in the same run that computed it). When present and non-empty for a given
apartment, the report shows: distance and estimated travel time per mode (walking,
cycling, driving, public transport, straight-line), each with its own confidence and
calculation method; and nearby-service counts per category, with confidence. An
apartment with a completely empty `GeoEnrichment` (no coordinates, or no curated
reference point for its location) omits the section entirely — never a fabricated
placeholder, the same convention `_render_analysis()`/`_render_ai_summary()` already
follow.

## Known, honestly-documented overlap

Three existing Analysis Engine analyzers (`walking_distance.py`, `public_transport.py`,
`nearby_amenity.py`) already compute conceptually similar facts, using the same
underlying math (`haversine_km`) and the same `knowledge_entries` convention this
engine's own `HaversineGeoProvider` reuses. They were **not** refactored to delegate
to `src/geography/` in this sprint — redesigning already-working, already-tested Step
6 code without a concrete need to do so would risk destabilizing it for no requested
benefit (this sprint's mission never asked for that consolidation). The duplication is
in *purpose* (both answer "how far/how walkable"), not in underlying logic (both
genuinely reuse the same `haversine_km` function and the same curated-data lookup
convention — no comparison or distance formula was written twice). Consolidating the
three analyzers to call into `src/geography/` instead is a reasonable future refactor,
explicitly not done here.

## Future extensions

- **A real routing/places provider** — Google Maps, Mapbox, OSM Overpass, a transit
  API, or several simultaneously with `ProviderRouter`-style fallback (the same
  pattern `src/providers/` already established for data/AI providers). Zero change
  needed to `GeographicEngine`/`GeoProviderFactory`/the calculators — only a new file
  implementing `GeoProvider` and one registration call.
- **Ranking integration** — once a production provider makes distance/nearby numbers
  trustworthy enough to weight, a new ranking factor could consume the same
  `GeoResult`/`NearbyPlace` shapes this sprint already defines.
- **Filter Engine evidence** — the already-built dormant distance/amenity filters
  become real, evidence-backed filters once this engine's own prerequisites
  (coordinates, curated reference points) exist for a given location at scale.
- **Multi-segment routing** — `Route`/`RouteSegment` are already shaped for a provider
  capable of real waypoints/turns; today's `RouteCalculator` only ever produces one
  segment because no such provider is integrated.

## Tests

78 new tests: unit tests for every new class (`GeoCache`, `GeoProviderRegistry`,
`GeoProviderFactory`, `DistanceCalculator`/`TravelTimeCalculator`/`RouteCalculator`,
`NearbySearch`, `HaversineGeoProvider`, `GeographicEngine`, `GeoStatistics`,
`GeoHistory`, the shared models), cache expiry/invalidation/configurable-TTL tests,
plugin tests (a second, independent `GeoProvider` registered at test time, resolved
with zero other code changed), distance/travel-time tests against real haversine math
and real, documented average-speed constants, agent-level integration tests (real
Playwright-fixture pipeline, mocked at the `BrowserCollector` boundary per
`tests/core/test_filter_engine_integration.py`'s own precedent) proving the default
(no `geo_engine`) path is unaffected and the opt-in path runs without crashing even
when the demo fixture's listings honestly have no coordinates, and report-generator
tests proving real evidence renders and missing evidence is omitted, never fabricated.
640 tests total (562 existing untouched + 78 new).
