# 25 — Dynamic Filter Engine

Status: **Live as of v2.5 Step 9 (2026-07-15)** — see `src/filter_engine/`.

## Preliminary Questions

**1. Why filters should be modular.** A hardcoded filter means adding one means
editing whatever runs all of them — exactly the coupling every other v2.0/v2.5
subsystem in this project has avoided (a new connector never touches the SDK, a new
analyzer never touches the pipeline, a new provider never touches the router). A
filter is a single, independent yes/no rule; the engine's only job is running
whichever ones are registered, deterministically, regardless of what each one checks.

**2. Why filtering is separated from connectors.** A connector's job is "did this
platform's listing get fetched and normalized correctly" — nothing about whether a
renter wants a 2-bedroom under $2000 depends on which platform the listing came
from. Separating them means every filter works identically regardless of data
source, and a connector never needs to know which filters exist.

**3. How future filters can be added.** The same self-registration pattern already
proven three times this project (`ConnectorRegistry`, `AnalysisRegistry`,
`ProviderRegistry`): subclass `BaseFilter`, call `register_filter(...)`, add one
import line to `filters/__init__.py`. `FilterEngine`/`FilterFactory` never name a
specific filter.

**4. How user preferences integrate with filters.** Through `SearchRequest.criteria`,
unchanged in shape — a user's preference is a value for a registered filter's key,
exactly the `{key: value}` or `{key: {"value": ..., "weight": ...}}` convention
`search/criteria.py` already established. This sprint didn't invent a second input
format; it made that same dict resolve against a much larger registry (see "Backward
Compatibility" below).

**5. Why every filter must expose metadata.** So the engine, a future UI, and this
project's own `filter_definitions` table (designed in migration 0001 for exactly
this, unused until now) can discover what filters exist — key, category, value
type, applicability — without hardcoding a list anywhere. `sync_filter_definitions()`
persists every registered filter's metadata into that real table.

## Architecture

```
src/filter_engine/
  __init__.py            # public re-exports; imports filters/ -> self-registration
  base_filter.py           # BaseFilter (ABC), FilterContext
  metadata.py                # FilterMetadata
  configuration.py              # FilterConfiguration
  result.py                       # FilterResult
  registry.py                       # FilterRegistry, register_filter()
  factory.py                          # FilterFactory
  composition.py                        # FilterCondition/FilterGroup/FilterOperator, evaluate()
  validator.py                            # FilterValidator (single, canonical validation path)
  statistics.py                             # FilterStatistics, compute_filter_statistics()
  history.py                                  # FilterHistoryEntry, record/get_filter_execution
  sync.py                                       # sync_filter_definitions()
  engine.py                                       # FilterEngine — the pipeline itself
  exceptions.py                                     # FilterException hierarchy
  filters/
    __init__.py                                       # eager imports -> self-registration
    core_filters.py                                     # 9 data-backed filters
    distance_filters.py                                   # 3 analysis-metric-backed filters
    dormant_base.py                                         # shared bases for dormant filters
    amenities.py                                              # 14 dormant amenity filters
    preferences_and_other.py                                    # 13 more dormant filters
```

39 built-in filters total: 12 genuinely data-backed, 27 dormant (see "Dormant
Filters" below).

## Filter Lifecycle

```python
class BaseFilter(ABC):
    key: str

    def validate(self, value) -> None: ...       # abstract — reject a malformed value
    def apply(self, apartment, value, context) -> bool: ...  # abstract — the yes/no decision
    def metadata(self) -> FilterMetadata: ...     # abstract — declarative self-description

    def supports(self, apartment) -> bool: ...    # default True — applicability gate
    def description(self) -> str: ...             # default: metadata().description
    def default_value(self): ...                    # default None
    def serialize(self, value): ...                   # default identity
    def deserialize(self, raw): ...                     # default identity
```

Only three methods are genuinely abstract — the same reasoning `BaseAnalyzer` (v2.0
Step 6) used: a filter's whole job is one computation, not a multi-stage sequence
like `BaseConnector`'s fetch/parse/normalize/validate. A filter that needs nothing
beyond a match rule implements three methods and inherits five, exactly like a
connector implements four hooks and inherits the rest of `BaseConnector`.

`FilterContext` (`conn`, `analysis_results`) is what a filter may need beyond the one
`Apartment` it's evaluating — mirrors `AnalysisContext`'s same reasoning. Most
built-in filters never touch it; `image_count` reads `conn` (real `apartment_images`
rows); the three distance filters read `analysis_results` (the *same* dict
`core/agent.py` already builds via `AnalysisEngine.analyze()` in the same run, never
a second database round-trip).

## Filter Pipeline

```
User Request (SearchRequest.criteria, a flat dict — or an explicit FilterGroup)
  ↓
Validation      — FilterValidator walks every leaf condition, calling its own
                   validate(); a bad request (unknown key, disabled key, malformed
                   value) fails immediately, before any apartment is touched.
  ↓
Normalization   — extract_value() unwraps the existing {"value": ..., "weight": ...}
                   convention; a flat dict becomes an implicit AND FilterGroup.
  ↓
Execution       — evaluate() walks the (possibly nested) FilterGroup tree for every
                   apartment, in list order — deterministic by construction (Python
                   lists/dataclass fields preserve insertion order), never by an
                   added sorting step.
  ↓
Statistics      — compute_filter_statistics() derives match/exclusion counts and
                   per-filter pass rates from the results just produced.
  ↓
Results         — FilterResult per apartment (matches + per-filter breakdown);
                   FilterHistory persists (search id, filter set, execution time,
                   results count, statistics) into filter_execution_history
                   (migration 0005).
```

`FilterEngine` has two entry points sharing one execution core: `run(apartments,
criteria, context)` (the flat-dict case, backward-compatible with
`search.criteria.apply_filters()`'s existing contract) and `run_group(apartments,
group, context)` (an explicit `FilterGroup` for AND/OR/NOT/nesting). `filter_apartments()`
is the convenience wrapper returning just the matched apartments, in original order —
a drop-in replacement anywhere `search.criteria.apply_filters()`'s return shape is
expected.

## Filter Composition

```python
FilterGroup(FilterOperator.OR, [
    FilterCondition("max_price", 1500),
    FilterGroup(FilterOperator.AND, [
        FilterCondition("property_type", "house"),
        FilterCondition("min_price", 1000),
    ]),
])
```

`AND`/`OR` accept any number of children (including nested `FilterGroup`s, to any
depth); `NOT` requires exactly one (De Morgan's already expresses `NOT` over multiple
conditions via nested `AND`/`OR`, so a multi-child `NOT` would be a second way to say
the same thing, not a new capability — `evaluate()`/`FilterValidator` both reject it
with `FilterConfigurationError`/a validation error respectively). An unsupported
filter (`supports(apartment)` returns `False`) is treated as "not applicable" — never
"excluded" — the same convention a dormant filter's `apply()` always returning `True`
already establishes.

`build_group_from_criteria()` is the implicit case: a flat dict becomes one `AND`
group, exactly reproducing `search.criteria.apply_filters()`'s "every key must match"
contract — future rule expansion (a new operator, a weighted composition) has one
place to grow from (`FilterOperator`), not a rewrite of `evaluate()`'s dispatch.

## Plugin System

`FilterRegistry` mirrors `AnalysisRegistry`/`ProviderRegistry`'s self-registration +
eager-import shape (a small, known set of filters, all always candidates — unlike
`ConnectorRegistry`'s lazy per-platform imports, which exist because *which*
connector is needed isn't known until a specific platform is targeted). Filters
register **instances**, not classes: no built-in filter has any per-search
construction parameter, so one shared instance per filter, registered once at import
time, is correct and simpler than `ConnectorRegistry`'s per-instantiation model.

Adding a filter requires editing exactly one file beyond the new filter module
itself: the relevant `filters/__init__.py`'s eager-import list. `FilterEngine`,
`FilterFactory`, `FilterRegistry`, and every existing filter are completely
untouched — proven the same way the SDK Validation Sprint (docs/22) proved it for
connectors: `git status` after this sprint shows every filter file as new, none of
the framework files needing to change per filter added.

## Backward Compatibility — the `search.criteria` Fallback

`SearchRequest.criteria` validation (`SearchRequest.__post_init__` →
`search.criteria.validate_criteria()`) predates this sprint and is tied to
`search/criteria.py`'s own, much smaller registry (`max_price`, `min_price`,
`min_bedrooms`, `min_bathrooms`, `min_sqft`). Rather than fork `SearchRequest`'s
validation into two incompatible paths, `search/criteria.py`'s `get_filter()` (and
therefore `validate_criteria()`/`apply_filters()`, which both call it) now falls back
to `FilterRegistry` for any key it doesn't already own itself — a **deferred**
import (inside the function body, not at module load) specifically to avoid a
circular dependency: `filter_engine`'s own `core_filters.py` imports `search.criteria`
to reuse `max_price`/`min_price`/`min_sqft`'s already-correct comparison logic rather
than duplicating it. The result: any of the 39 new filters is usable via
`SearchRequest.criteria` immediately, with zero changes to `SearchRequest` itself,
and the original 5 keys resolve exactly as before (checked first, unchanged
priority). `registered_keys()` now returns the union of both registries (42 unique
keys — `max_price`/`min_price` are registered in both, so the union is smaller than
the sum).

## Integration

```
Provider Framework → Connector SDK → Research Agent
  ↓ (Apartment History, Search Memory)
Deep Analysis Engine
  ↓
Dynamic Filter Engine   [optional — see below]
  ↓
Ranking Engine
  ↓
HTML Report
```

`RentalResearchAgent.__init__` gained one new, optional, default-`None` parameter:
`filter_engine: FilterEngine | None = None` — every existing caller (every test that
doesn't pass it) is byte-identical to before this sprint. When supplied,
`RentalResearchAgent.run()` re-filters `apartments` right after the Deep Analysis
Engine runs (so `analysis_results` exists) and before `RankingEngine.rank()`, with a
**real** `FilterContext` (this run's own `conn` and `analysis_results` — not the
empty context `search.criteria`'s fallback uses), and records `FilterHistory`.
`RankingEngine.rank()` still runs its own (unchanged) `apply_filters()` pass
afterward — safe and idempotent, since `FilterEngine`'s output is always a subset of
its input, and no dormant/context-less filter can newly exclude an apartment that
already passed. `ui/cli.py` gained one new, off-by-default flag:
`--use-filter-engine`.

This mission's own diagram placed "Filter Engine" before "Research Agent" — read
literally, that would mean filtering the *request* before any listing exists to
filter. The actual, useful integration point is the same one `search.criteria.
apply_filters()` already occupied (after collection, before ranking) — moving it
earlier would mean filtering nothing, since no apartment exists yet at that point in
the pipeline. This is the same kind of diagram-vs-implementation reconciliation v2.0
Step 6 (Deep Analysis Engine) already made explicitly, for the same reason: the
mission's diagram describes *conceptual* ordering, not literal call order.

## Metrics & History

`FilterStatistics` (computed by `compute_filter_statistics()`, never inside
`FilterEngine` itself) — total/matched/excluded counts, overall match rate, and a
per-filter-key pass rate distinct from the composed outcome (a filter can pass
individually often while the overall AND still excludes most apartments, if it's
combined with a stricter one). `FilterHistoryEntry` (search id, filter set,
execution time, total apartments, matched count, statistics) persists into
`filter_execution_history` (migration 0005) — a genuinely new table, since nothing
existing tracked *filter-specific* execution stats (`search_requests.criteria_json`
already stores the filter set used, but not what happened when it ran).

## Dormant Filters

27 of the 39 built-in filters — every amenity flag (private bathroom, air
conditioning, parking, ...), every room/flatshare preference (gender, student/
professional friendly), structured geography (country/region/city — only
`Apartment.address_raw` free text exists today), stay duration/availability date,
room type, flatmate count, and radius — reference fields that **do not exist**
anywhere in `Apartment`/`RawListing`/`SearchRequest`. This connects directly to the
"room/flatshare filter categories" tension flagged and deliberately deferred
throughout this project's history (`learning/architecture_notes.md`'s 2026-07-14
entry) and the SDK Validation Sprint's Finding 1 (docs/22: `room_type` was requested
by an earlier mission but never added to the schema).

Every dormant filter is real, registered, and tested — not stubbed out or skipped.
Each one's `apply()` always returns `True` (never fabricates an exclusion on data
that doesn't exist, the same convention `RawListing`'s honest `None` fields and the
Analysis Engine's `score=None` already established), while `validate()` still
enforces the *value*'s own shape (a boolean filter still rejects a non-boolean
value) — a dormant filter is honestly inert, not silently permissive of garbage
input. `FilterMetadata.is_dormant=True` and each one's `description()` state this
plainly, so a caller inspecting the registry (or the persisted `filter_definitions`
table) can tell which filters are real today without reading source code.

Building real data support for any of these 27 is a product-scope decision this
sprint doesn't make — it's the same "room/flatshare" question this project has
raised and deferred every time it's come up, not a new one this sprint invented.

## Best Practices

- A new filter needing more than the bare `Apartment` object should extend
  `FilterContext` (adding a field, never removing one) rather than smuggling extra
  state through a global or a filter's own constructor.
- Reuse existing logic (`search.criteria.FilterDefinition`, `src.knowledge.metrics`,
  `src.analysis`'s stored scores) wherever a filter's comparison already exists
  somewhere else in the codebase — see `_LegacyCriteriaFilter`/`_AnalysisScoreFilter`
  for the two patterns this sprint established for exactly this.
- A dormant filter is not a lesser citizen: give it a real `FilterMetadata`
  (`is_dormant=True`, an honest `description()`), real `validate()` value-shape
  checking, and a real test — the same rigor a data-backed filter gets.
- Never invent a raw distance/time unit a stored metric doesn't actually provide
  (see `distance_filters.py`'s own docstring) — state the real unit (a `[0,1]`
  score, here) rather than implying accuracy that doesn't exist.

## How to Create a New Filter

1. Subclass `BaseFilter` (or one of the shared bases in `dormant_base.py` /
   `_LegacyCriteriaFilter` / `_AnalysisScoreFilter` if it fits an existing shape), set
   `key`, implement `validate()`/`apply()`/`metadata()`.
2. Call `register_filter(YourFilter())` at the bottom of the module.
3. Add the module to the relevant `filters/__init__.py`'s eager-import list.
4. Write tests: `validate()`'s accept/reject cases, `apply()`'s match/exclude cases
   (and its no-evidence/dormant case if applicable), and confirm registration.
5. If the filter is genuinely data-backed, consider whether `FilterContext` needs a
   new field first (see "Best Practices").

## Tests

103 new tests: registry/factory/configuration/composition (AND/OR/NOT/nested,
deterministic order, unsupported-filter handling) — 24; engine (flat-dict and
group entry points, validation propagation, dormant/context-dependent behavior) —
12; validator (criteria and group paths, nested error discovery) — 12; statistics —
5; history (real DB round-trip) — 3; sync (`filter_definitions` persistence) — 3;
the 12 data-backed filters' own real behavior (including `image_count`/distance
filters' context-dependence) — 20; the 27 dormant filters (inventory + shared-base
behavior) — 14; performance (500 apartments × real filters; 500 additional
registered filters) — 2; agent-level integration (real pipeline, `FilterHistory`
persisted, default path unaffected) — 4; plus 7 new tests in the pre-existing
`tests/search/test_criteria.py` proving the fallback. 562 tests total (460 existing
untouched + 102 new — some overlap in the count above reflects tests spanning more
than one category). Full pre-existing suite passes unmodified.

## Related

- [22_SDK_Validation_Sprint.md](22_SDK_Validation_Sprint.md) — the independence/
  zero-change-extensibility audit methodology this sprint's plugin system follows
- [19_Analysis_Engine.md](19_Analysis_Engine.md) — `BaseAnalyzer`'s "thin contract,
  not a template method" precedent `BaseFilter` mirrors
- [04_Search_Request.md](04_Search_Request.md) — `SearchRequest.criteria`'s existing
  shape, unchanged by this sprint
- `learning/architecture_notes.md` — the 2026-07-14 "room/flatshare filter
  categories" deferral this sprint's dormant filters connect back to
