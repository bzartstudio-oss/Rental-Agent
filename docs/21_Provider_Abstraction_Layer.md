# 21 — Provider Abstraction Layer

Status: **Live (2026-07-15)** — see `src/providers/`. Not one of the numbered "Version
2.0" implementation steps in [10_Roadmap.md](10_Roadmap.md) — a separate, orthogonal
capability requested afterward, sitting on top of the Connector SDK (v2.0 Step 5) and
the First Production Connector (v2.0 Step 7) rather than replacing anything either one
already does.

## Why This Exists

Every connector (v2.0 Step 5) already knows how to fetch/parse/normalize/validate one
platform's listings, and `RentalResearchAgent` already queries every
`connector_available` platform and aggregates whatever succeeds (v1.0's Multi-Platform
Discovery Framework design — "no website-specific logic outside connectors," proven
again in v2.0 Step 7). What didn't exist until now: a way to say *"prefer this data
source, but automatically use a different one if it's unavailable or fails, and pick
whichever one is genuinely best by some measurable standard rather than always
querying everything."* That's a selection/preference problem, not a fetching problem —
a new, thin layer above the Connector SDK, not a replacement for it. The same
selection problem exists for an entirely new, optional capability this sprint also
introduces: AI-generated search summaries, which need the same "prefer the best
available option, fall back if it's not there or fails" logic but have nothing to do
with fetching listings at all — hence one common `Provider` abstraction serving two
different kinds (`DataProvider`, `AIProvider`), not two unrelated systems.

## Architecture

```
src/providers/
  __init__.py           # imports data/ and ai/ -> self-registration
  base.py                 # Provider (ABC), ProviderKind (DATA/AI)
  scoring.py                # ProviderMetadata, ScoringWeights, ProviderScore, score_provider()
  registry.py                 # ProviderRegistry, register_provider()
  router.py                     # ProviderRouter, ProviderRunOutcome, ProviderAttempt
  exceptions.py                   # ProviderException, NoProviderAvailableError, ProviderConfigurationError
  data/
    __init__.py                    # imports both -> self-registration
    base_data_provider.py             # DataProvider(Provider) — adds platform_id, search()
    rentcast_data_provider.py           # wraps RentCastConnector via ConnectorFactory
    local_demo_data_provider.py           # wraps DemoPlatformConnector, always available
  ai/
    __init__.py
    base_ai_provider.py                     # AIProvider(Provider) — adds summarize()
    ollama_ai_provider.py                     # real HTTP to a local Ollama server
    null_ai_provider.py                         # always available, honest None summary
```

No provider does its own fetching/parsing/HTTP-from-scratch work that a lower layer
already does correctly: `RentCastDataProvider`/`LocalDemoDataProvider` are thin
adapters over `ConnectorFactory.get(platform).search(request)` — exactly one place
(the Connector SDK) knows how to actually talk to RentCast or parse the demo fixture.
`OllamaAIProvider` is the one genuinely new piece of transport logic in this sprint,
since nothing in this codebase talked to an LLM before.

## Common Interface

```python
class Provider(ABC):
    provider_id: str
    kind: ProviderKind          # DATA or AI, set by the narrower base class

    def is_available(self) -> bool: ...   # cheap, no side effects, no real fetch
    def metadata(self) -> ProviderMetadata: ...  # static cost/freshness/quality
```

`DataProvider(Provider)` adds `platform_id` (the real `platforms.id` row its results
should be attributed to — not always equal to `provider_id`, see "A Naming Wrinkle"
below) and `search(request) -> ConnectorResult` — the exact same return shape
`BaseConnector.search()` already produces, so a `DataProvider` is a selection layer,
never a competing result type. `AIProvider(Provider)` adds
`summarize(ranked, request) -> str | None` — `None` is an honest "nothing to say,"
never a fabricated placeholder, the same convention the Deep Analysis Engine (v2.0
Step 6) established for `score=None`.

## Registry — Self-Registration, Eager Import

`ProviderRegistry` mirrors `ConnectorRegistry` (v2.0 Step 5) and
`AnalysisRegistry` (v2.0 Step 6)'s self-registration idea, but is deliberately simpler
than `ConnectorRegistry`: connectors are lazily imported per-platform on demand
(`ConnectorFactory.get()` doesn't know which platform it needs until a specific search
targets it); every provider of a given kind is a candidate on *every* routing
decision, so there's no "which one do I need this time" question to defer —
`src/providers/data/__init__.py`/`src/providers/ai/__init__.py` eagerly import every
built-in provider module once, exactly like `src/analysis/analyzers/__init__.py`
already does for analyzers. Providers register **instances**, not classes — a provider
has no per-search construction parameter (unlike a connector, which takes a
`ConnectorConfiguration`), so one shared instance per provider is correct, not a
simplification that loses anything.

## Scoring Model

`ProviderMetadata` (`cost_score`, `freshness_score`, `quality_score`, each `[0, 1]`) is
a provider's static self-description. `score_provider(metadata, available, weights)`
combines all four factors the mission named explicitly — availability, cost,
freshness, quality — into one number:

```
score = w_availability * (1.0 if available else 0.0)
      + w_cost * (1.0 - cost_score)        # inverted: lower cost scores higher
      + w_freshness * freshness_score
      + w_quality * quality_score
```

Default weights: `availability=0.1, cost=0.25, freshness=0.3, quality=0.35` (sums to
`1.0`, a convention not an enforced constraint — `ProviderRouter(kind, weights=...)`
accepts any `ScoringWeights`, matching the "weights are data, not hardcoded logic"
convention `ranking/scoring.py`/`analysis/scoring.py` already established).

**Availability is a hard gate, not just a weighted term.** `ProviderRouter.
ranked_candidates()` excludes any provider whose `is_available()` is `False`
*before* scoring — an unavailable provider is never ranked, never a fallback
candidate, regardless of how good its cost/freshness/quality might be. This means
every provider that *does* get scored has `available=True`, so the availability
component is a constant `w_availability` for all of them — mathematically inert for
ranking *among* available candidates, but still real and shown in every log line, so
"why did this provider score what it did" is always fully auditable, availability
included, not hidden.

## Built-In Providers

| Provider | Kind | `is_available()` | cost / freshness / quality |
|---|---|---|---|
| `RentCastDataProvider` | data | `RENTCAST_API_KEY` env var set | 0.2 / 0.9 / 0.85 |
| `LocalDemoDataProvider` | data | always `True` | 0.0 / 0.1 / 0.3 |
| `OllamaAIProvider` | ai | real `GET /api/tags` against a local Ollama server | 0.0 / 1.0 / 0.6 |
| `NullAIProvider` | ai | always `True` | 0.0 / 1.0 / 0.0 (lowest possible — never outranks a real, available AI provider) |

With no `RENTCAST_API_KEY` and no local Ollama running — the zero-configuration
case — `ranked_candidates()` for data returns only `LocalDemoDataProvider`, and for AI
only `NullAIProvider`. This is what makes "the first version works without any API
key" literally true, not just documented intent.

### A Naming Wrinkle: `provider_id` vs. `platform_id`

`LocalDemoDataProvider.provider_id == "local_demo"` but its underlying, real
`platforms.id` row is `"demo_platform"` — the same row every existing demo-connector
test already uses. `DataProvider.platform_id` exists specifically to carry this
distinction: `provider_id` is this provider's registry key and log identity;
`platform_id` is what `apartments.platform_id`/`platform_performance_observations.
platform_id` (both real foreign keys to `platforms(id)`) must actually contain.
`core/agent.py`'s router integration always resolves through `platform_id`, never
assumes it equals `provider_id`.

## Router & Fallback

```python
router = ProviderRouter(ProviderKind.DATA)          # or ProviderKind.AI
outcome = router.run_with_fallback(
    lambda provider: provider.search(request),       # or provider.summarize(...)
    is_success=lambda result: result.success,        # optional; defaults to "didn't raise"
)
```

`run_with_fallback()`:
1. Ranks every *available* provider of this router's kind, best-scored first
   (`ranked_candidates()`).
2. Tries `operation(provider)` on each, in order. A provider "fails" either by
   raising or by its result failing the `is_success` check (a data provider
   returning `ConnectorResult(success=False, ...)` — not an exception, but still
   unusable) — either way, logged and the next candidate is tried.
3. Returns a `ProviderRunOutcome(provider_id, result, attempts)` for the first
   success — `attempts` is the full trail (every provider tried, its score, whether
   it succeeded, and why not if it didn't), so a caller or test can confirm exactly
   what happened, not just the final winner.
4. Raises `NoProviderAvailableError` only once every available candidate has been
   tried and none succeeded (or none were available to begin with).

**Logging.** Every `run_with_fallback()` call logs the full ranked candidate list
(provider id + score) before attempting anything, then logs each attempt's outcome
and the final selection with its reason — via `src/utils/logging.py`'s structured
JSON logger (introduced in v2.0 Step 7). This directly satisfies "logging that reports
which provider was selected and why": the "why" is the actual computed score, not a
restated intention.

## Integration

**`RentalResearchAgent.__init__`** gained two new, optional, default-`None`
parameters: `data_router: ProviderRouter | None`, `ai_router: ProviderRouter | None`.
Every existing caller (every test that doesn't pass them) gets byte-identical
behavior to before this sprint — proven by `tests/core/test_agent.py` and the rest of
the pre-existing suite passing completely unmodified.

- **`data_router` given**: `RentalResearchAgent.run()` calls
  `data_router.run_with_fallback(lambda provider: provider.search(request), is_success=lambda r: r.success)`
  once, attributes the result to the resolved provider's real `platform_id`, and
  writes it through `analyzers/engine.py::process_listings()` exactly like any other
  platform's result. The platforms this router manages (`rentcast`, `demo_platform`)
  are then excluded from the normal per-platform loop, so they're never queried
  twice — **any other registered platform is completely unaffected** and still runs
  through the unchanged loop. If the router's resolved platform isn't registered in
  `platforms` yet (a real foreign-key precondition, same as any connector), this is
  reported as an honest error entry with zero apartments, never a crash.
- **`ai_router` given**: after ranking, `RentalResearchAgent.run()` calls
  `ai_router.run_with_fallback(lambda provider: provider.summarize(ranked, request))`
  once and passes the result (or `None`) to `generate_report(..., ai_summary=...)` — a
  new, optional, backward-compatible parameter on `services/report_generator.py::generate_report()`,
  the same shape v2.0 Step 6 already established for `analysis_results`. `None`
  renders no summary section at all.
- **`ui/cli.py`** gained one new, off-by-default flag: `--use-provider-router`. When
  passed, both routers are constructed with their default registry/weights and
  handed to `RentalResearchAgent`; when omitted (the default), neither router exists
  and the CLI's behavior is identical to before this sprint.

No module downstream of `core/agent.py` (`analyzers/`, `ranking/`, `services/`,
`storage/`) contains any Provider-specific code — a router-selected result flows
through `process_listings()`/ranking/report generation exactly like a directly-queried
connector's result would.

## Failure Behavior

Every layer degrades honestly rather than crashing:

- A `DataProvider.search()` that raises, or returns a failed `ConnectorResult`, is
  caught by `run_with_fallback()` and the next-ranked provider is tried.
- Every available data-provider candidate failing raises `NoProviderAvailableError`,
  caught by `RentalResearchAgent.run()` and recorded as an error entry — zero
  apartments from the router path, the rest of the pipeline (any non-router
  platform, ranking, report generation) proceeds normally.
- An `AIProvider.summarize()` that raises is likewise caught and the next AI
  provider tried; since `NullAIProvider` is always available and never raises, the
  AI side of `run_with_fallback()` only ever raises `NoProviderAvailableError` if a
  caller constructs a router against a registry with `NullAIProvider` removed —
  not a real configuration this codebase produces.

## Tests

- `tests/providers/test_scoring.py` — the pure scoring function: availability gating,
  cost inversion, freshness/quality ordering, weight defaults.
- `tests/providers/test_registry.py` — register/get/all/is_registered/reset, rejecting
  a non-`Provider` or a `Provider` with no `provider_id`.
- `tests/providers/test_router.py` — **the fallback logic itself**, using small
  scripted fake providers (the same "fake connector" strategy
  `tests/connectors/sdk/test_base_connector.py` already uses): ranking excludes
  unavailable providers, higher quality ranks first, falls back on a raised
  exception, falls back on an `is_success`-failed result, raises
  `NoProviderAvailableError` when every candidate fails or none are available.
- `tests/providers/data/` / `tests/providers/ai/` — each built-in provider's own
  `is_available()`/`metadata()`/delegation logic, with `RentCastDataProvider`'s
  `ConnectorFactory` call and `OllamaAIProvider`'s HTTP calls fully mocked.
- `tests/core/test_provider_integration.py` — the full-pipeline proof: no API key
  routes to `local_demo`; a working RentCast is preferred when configured; RentCast
  failing mid-run falls back to `local_demo` in the *same* run; the default
  (no-router) path is unaffected; an AI summary appears in the report when a working
  AI provider is available, is omitted when none is, and a raising AI provider falls
  back to `NullAIProvider` rather than crashing the search. `local_demo`'s underlying
  browser fetch is mocked at the `BrowserCollector` boundary (reading the real local
  fixture file directly) so these tests aren't coupled to real-browser-launch timing
  — Playwright reliability itself is already proven extensively elsewhere
  (`tests/core/test_agent.py`, `tests/connectors/`).
- `tests/services/test_report_generator.py` gained an `AISummarySectionTests` class,
  mirroring the existing `AnalysisSectionTests`: renders when provided, omitted when
  `None`, HTML-escaped.

52 new tests; the full pre-existing suite (361 tests) passes completely unmodified.

## How to Add the Next Provider

**Updated by v2.5 Step 8** — see [24_Production_Providers.md](24_Production_Providers.md)
for the full current checklist (this section's steps 1–4 below are still accurate;
Step 8 added a `config` parameter to `search()`/`summarize()` and a
`ProviderFactory`/`ProviderValidator`/`ProviderHealth`/`ProviderMetrics`/
`ProviderStatistics` layer on top of what's described here).

1. Subclass `DataProvider` or `AIProvider`, set `provider_id` (and `platform_id` for a
   data provider), implement `is_available()`/`metadata()`/`search()` or
   `summarize()` (both now optionally accept a `ProviderConfiguration`).
2. Call `register_provider(YourProvider())` at the bottom of the module.
3. Add the module to `src/providers/data/__init__.py` or `src/providers/ai/__init__.py`'s
   eager-import list — the only place that ever needs to change; `ProviderRegistry`/
   `ProviderRouter` do not.
4. Write the same test shape this sprint used: `is_available()`/`metadata()` unit
   tests, a delegation test (mocking whatever transport the provider wraps), and — if
   it changes routing outcomes meaningfully — a `run_with_fallback()` scenario using
   scripted fakes (`tests/providers/test_router.py`'s pattern), not the real provider.

## Related

- [18_Connector_SDK.md](18_Connector_SDK.md) — the connector framework every built-in
  `DataProvider` wraps rather than reimplements
- [20_First_Production_Connector.md](20_First_Production_Connector.md) — RentCast,
  the connector `RentCastDataProvider` delegates to
- [19_Analysis_Engine.md](19_Analysis_Engine.md) — the `score=None`/no-fabrication
  convention `AIProvider.summarize()` follows for its own `None` case
- [01_System_Architecture.md](01_System_Architecture.md) — module table entry for
  `providers/`
