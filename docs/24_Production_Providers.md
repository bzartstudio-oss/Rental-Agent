# 24 — Production Provider Framework

Status: **Live as of v2.5 Step 8 (2026-07-15)** — see `src/providers/`.

Note on scope: this doc covers what v2.5 Step 8 *added* — `ProviderFactory`,
`ProviderConfiguration`, `ProviderHealth`, `ProviderMetrics`, `ProviderStatistics`,
`ProviderValidator`. `ProviderRegistry`, `ProviderRouter`, and the scoring model
already existed (Provider Abstraction Layer, docs/21) and are **reused, not
recreated** — see "What Already Existed" below for why the mission's "Create
ProviderRegistry" line doesn't mean a second one was built.

## What Already Existed

`docs/21_Provider_Abstraction_Layer.md` built the foundation this sprint completes:
`Provider`/`ProviderKind`, `ProviderRegistry` (self-registration), `ProviderRouter`
(scoring + fallback), `ProviderMetadata`/`ScoringWeights`, and the four built-in
providers (`RentCastDataProvider`, `LocalDemoDataProvider`, `OllamaAIProvider`,
`NullAIProvider`). Rebuilding any of these now would be exactly the duplicated code
this sprint's own non-functional requirements forbid — every new class below either
wraps one of them or reuses the Knowledge Engine (v2.0 Step 4), never a second,
competing implementation.

## Architecture

```
src/providers/
  __init__.py          # public re-exports — mirrors src.connectors.sdk's own shape
  base.py                # Provider (ABC), ProviderKind          [docs/21]
  scoring.py               # ProviderMetadata, ScoringWeights, score_provider()  [docs/21]
  registry.py                # ProviderRegistry, register_provider()            [docs/21]
  router.py                    # ProviderRouter, ProviderRunOutcome/Attempt      [docs/21]
  exceptions.py                  # + ProviderValidationError (new this sprint)
  configuration.py                 # ProviderConfiguration            [NEW]
  factory.py                        # ProviderFactory                 [NEW]
  health.py                           # ProviderHealth, check_provider_health()  [NEW]
  metrics.py                            # ProviderMetrics, build_/record_provider_metrics()  [NEW]
  statistics.py                           # ProviderStatistics, provider_statistics()  [NEW]
  validator.py                              # ProviderValidator, ProviderValidationResult  [NEW]
  data/, ai/                                  # concrete providers                [docs/21]
```

## Preliminary Questions

**1. Why production providers are separated from the SDK.** The Connector SDK
(`connectors/sdk/`) is the fetch/parse/normalize/validate mechanism for exactly one
platform. A provider is a *selection* layer above it — which source to use, and in
what order of preference — a different concern with a different failure mode (a
connector fails to fetch; a provider fails to choose well). A platform's SDK
integration never needs to know it might be one of several competing choices; the
selection logic never needs to know how any platform is actually fetched.

**2. How providers remain independent.** Same guarantee already empirically proven
for connectors (SDK Validation Sprint, docs/22): every provider imports only its own
base class, the Connector SDK, and generic utilities — never another provider.
Verified again for this sprint's new components: `ProviderFactory`/`ProviderHealth`/
`ProviderMetrics`/`ProviderStatistics`/`ProviderValidator` each operate on *one*
`Provider` passed as an argument — none of them import a specific provider module,
so adding provider #5 requires no change to any of them.

**3. How future providers can be added with zero changes to existing providers.**
Exactly the process docs/21 already established, unchanged: subclass `DataProvider`/
`AIProvider`, implement `is_available()`/`metadata()`/`search()` or `summarize()`,
call `register_provider(YourProvider())`. `ProviderFactory.get(provider_id)` resolves
it by name alone — no registry, factory, or other provider file ever needs editing.

**4. How failures are isolated.** Two distinct layers, not one. A connector's own
retry/timeout handling (e.g. `RentCastClient`'s backoff) recovers from *transient*
failures without the provider ever knowing — `ProviderConfiguration` now threads
`timeout_ms`/`max_retries`/`credentials` down into that same mechanism (a
`ConnectorConfiguration`, for data providers) rather than reimplementing it.
`ProviderRouter.run_with_fallback()` recovers from *persistent* failures by trying
the next-best provider — isolating one provider's outage from the rest of the
search, already proven this session against a real RentCast 403 (docs/21).

**5. How provider reliability will be measured.** By reusing the Knowledge Engine,
not building a second measurement system. `ProviderMetrics` is one run's numbers,
computed by the same `src.knowledge.metrics` formulas every connector's run already
uses. `ProviderHealth`/`ProviderStatistics` are thin, read-only views over
`knowledge_service.connector_health()`/`platform_statistics()` — the exact same
`platform_performance_observations` rows a directly-queried connector's run already
produces.

## Provider Lifecycle

```
ProviderFactory.get(provider_id) -> Provider          # resolution, mirrors ConnectorFactory
provider.is_available()                                # availability verification
provider.metadata()                                     # static self-description (for scoring)
provider.search(request, config)                          # DataProvider — pagination/retry/timeout
  or provider.summarize(ranked, request, config)            # AIProvider
ProviderValidator.validate(provider, result)                  # provider-level validation
check_provider_health(provider, conn)                           # current + historical health
build_provider_metrics(provider_id, platform_id, result)          # one run's metrics
provider_statistics(provider, conn)                                 # aggregate reliability view
```

**`ProviderConfiguration`** (`configuration.py`) mirrors `ConnectorConfiguration`
deliberately: `timeout_ms`, `max_retries`, `rate_limit_per_minute`, `credentials`.
Passed into `search()`/`summarize()` (both default it to `None` — every call site
written before this sprint, including every `ProviderRouter.run_with_fallback()`
lambda, keeps working unchanged). A `DataProvider` translates it into a
`ConnectorConfiguration` at the one point it calls `ConnectorFactory.get()`;
`OllamaAIProvider` uses `config.timeout_ms` to override its request timeout. Neither
reimplements retry/backoff/pagination — those stay exactly where they already lived
(`RentCastClient`, `RentCastConnector`).

**`ProviderFactory`** (`factory.py`) is a thin, one-line delegation to
`ProviderRegistry.get()` — simpler than `ConnectorFactory` because providers are
registered once as singletons (no per-search construction parameter, unlike a
connector), not because it does less validation. It exists so callers depend on
"ask the factory for a provider," the same habit `core/agent.py` already has for
connectors, rather than reaching into the registry directly.

## Provider Health

`ProviderHealth` (`health.py`) has exactly one field `ConnectorHealth` doesn't:
`is_available_now`, a live `provider.is_available()` call — the same fact
`ProviderRouter` gates candidacy on. Everything else (`connector_health`) is the
*same* `ConnectorHealth` object `BaseConnector.health_check()` already returns,
looked up under the provider's `platform_id`. An `AIProvider` (no `platform_id`) gets
`platform_id=None`/`connector_health=None` — an honest "not applicable," not an
error. A `DataProvider` whose platform has zero observations yet gets
`connector_health=None` too — "no evidence yet," never a fabricated zero.

## Metrics

`ProviderMetrics` (`metrics.py`) covers the mission's list — execution time, success/
failure, listing count, duplicate rate, parsing quality (extraction/image/
availability) — all computed by `build_provider_metrics()` calling the *same*
`src.knowledge.metrics` functions every connector's run already uses:
`extraction_quality_score`, `image_quality_score`, `availability_quality_score`,
`duplicate_rate`. "Duplicate count" (the mission's phrase) is represented as a rate,
matching the one shape this project's Knowledge Engine has ever stored
(`platform_performance_observations.duplicate_rate`, migration 0001) — introducing a
second, raw-count column would be new schema this sprint doesn't call for.
"Response statistics" for *one* run is `execution_time_ms`; the aggregate view
(average/min/max across many runs) is `ProviderStatistics`' job.

`record_provider_metrics()` writes into `platform_performance_observations` via the
exact same `knowledge_service.record_platform_observation()` call every connector's
run already goes through — "Store observations inside the Knowledge Engine" (the
mission's words) is satisfied by reusing that one write path. **Not wired into
`core/agent.py`'s router integration** — `RentalResearchAgent.run()` already records
a router-selected platform's observation via its pre-existing `platform_metrics`
bookkeeping (docs/21 "Integration"); calling `record_provider_metrics()` there too
would double-write the same observation. Instead, `core/agent.py`'s
`_run_data_router()` calls `build_provider_metrics()` (computation only, no write)
and logs the result via `src.utils.logging` — real structured logging, satisfying
the mission's "structured logging"/"metrics collection" requirements, without a
duplicate database write. `record_provider_metrics()` remains available for any
caller using a provider standalone, outside the full agent pipeline (see its
docstring and `tests/providers/test_metrics.py`).

## Statistics

`ProviderStatistics` (`statistics.py`) is the aggregate, multi-run view — distinct
from `ProviderMetrics` (one run) and `ProviderHealth` (current point-in-time state).
`provider_statistics()` looks up `knowledge_service.platform_reliability()` under the
provider's `platform_id` and re-shapes the result; it recomputes nothing.

## Validation

`ProviderValidator` (`validator.py`) validates **provider-level** concerns,
deliberately distinct from `ConnectorValidator` (which validates *listing* fields and
already runs inside every `BaseConnector.search()` call — re-validating listings here
would be exactly the duplicated logic the mission's non-functional requirements
forbid). Two checks:

1. `validate_metadata()` — every score `score_provider()` consumes is documented as
   `[0, 1]` but was never enforced at the point a provider declares it; this is that
   enforcement.
2. `validate_result()` — surfaces (never re-derives) a data provider's already-
   computed `ConnectorResult.validation_warnings`.

`strict=True` raises `ProviderValidationError` instead of returning `is_valid=False`
— off by default, mirroring `ConnectorConfiguration.strict_validation`'s same
opt-in-only reasoning.

## Integration

```
Provider
  ↓ (DataProvider.search() delegates to ConnectorFactory.get(platform).search())
Connector SDK
  ↓ (BaseConnector.search() -> ConnectorResult)
Research Agent (core/agent.py, via data_router/ai_router — docs/21 "Integration")
  ↓
Apartment History → Search Memory → Knowledge Engine → Analysis Engine → Ranking → HTML Report
```

Unchanged from docs/21: `RentalResearchAgent`'s `data_router`/`ai_router` constructor
parameters remain optional, default `None`, byte-identical behavior for every
existing caller. This sprint's only functional addition to `core/agent.py` is the
`ProviderMetrics`-based structured log line described above — no other line in the
per-platform loop, Apartment History call, or Knowledge Engine recording changed.

## Maintenance Guidelines

- Never reimplement a formula that already exists in `src.knowledge.metrics` or a
  transport concern that already exists in a connector — every new provider-level
  helper in this sprint is a thin wrapper for exactly this reason.
- A new provider-level dataclass (health/metrics/statistics-shaped) should degrade to
  `None` for anything not applicable to its provider kind (an `AIProvider` has no
  `platform_id`) — never fabricate a zero or an empty-but-present object.
- `ProviderConfiguration` fields should stay a strict mirror of
  `ConnectorConfiguration`'s — if the SDK ever gains a new configuration knob, add
  the matching field here too, so a provider caller and a connector caller never see
  a different vocabulary for the same concept.

## Adding the Next Provider

Unchanged from docs/21's own checklist — subclass `DataProvider`/`AIProvider`,
implement the required methods (now including the optional `config` parameter),
register, add to the relevant `__init__.py`'s eager-import list, write the same test
shape this sprint used (`is_available`/`metadata` unit tests, a delegation test with
transport mocked, a config-threading test if the connector underneath has real
retry/timeout knobs).

## Tests

32 new tests: `ProviderConfiguration` defaults/overrides; `ProviderFactory`
resolution/singleton-identity/unknown-id; `ProviderHealth` for an AI provider, a
data provider with no observations, and one with real observations;
`ProviderMetrics` built from full/sparse/duplicate/failed `ConnectorResult`s plus a
real `record_provider_metrics()` write-through; `ProviderValidator` metadata-range
and connector-result-surfacing behavior, strict vs. non-strict; `ProviderStatistics`
for all three degradation cases; and config-threading (retry/timeout) tests proving
`ProviderConfiguration` genuinely reaches `RentCastDataProvider`'s
`ConnectorConfiguration` and `OllamaAIProvider`'s request timeout, not just existing
as an unused parameter. 460 tests total (428 existing untouched + 32 new).

## Related

- [21_Provider_Abstraction_Layer.md](21_Provider_Abstraction_Layer.md) — the
  foundation this sprint completes
- [18_Connector_SDK.md](18_Connector_SDK.md) — the mechanism every `DataProvider`
  delegates to
- [16_Knowledge_Engine.md](16_Knowledge_Engine.md) — the metrics formulas and
  observation store every new component here reuses
- [22_SDK_Validation_Sprint.md](22_SDK_Validation_Sprint.md) — the independence
  audit methodology reapplied to this sprint's new components
