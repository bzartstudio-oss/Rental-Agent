# 18 — Connector SDK & Plugin Framework

Status: **Live as of v2.0 Step 5 (2026-07-15)** — see `src/connectors/sdk/`.

Note on numbering: the mission for this sprint asked for `docs/17_Connector_SDK.md`,
but `17` was already taken by [17_Search_Memory.md](17_Search_Memory.md) (v2.0 Step 3).
This is `18` instead — the next free number, not a renumbering of anything existing.

## Why This Exists

Every rental platform exposes listings differently: some have a real API (JSON, maybe
GraphQL), most don't and need browser automation against server-rendered HTML, and a
few might only offer CSV exports or an RSS feed. Before v2.0 Step 5, each connector
(`demo_platform.py`, `demo_platform_two.py`) independently implemented the same
fetch -> save -> parse sequence — not platform-specific logic, just boilerplate
duplicated once per file. That's exactly the failure mode this SDK exists to prevent:
**adding a new rental platform must require creating one connector module with minimal
custom code, not re-deriving the whole pipeline every time.**

The deeper reason, restated from [01_System_Architecture.md](01_System_Architecture.md)
Principle 7: business logic (Analysis Engine, Ranking, Search Memory, Knowledge Engine)
must never depend on which website — or which *kind* of source — a listing came from.
`RentalResearchAgent.run()` calls `connector.search(request)` and gets back a
`ConnectorResult` whether the connector fetched HTML with Playwright, called a REST
API with `requests`, parsed a GraphQL response, or read a CSV export. Nothing
downstream branches on source type; nothing downstream *can*, because the shape
leaving every connector is identical.

## Who Depends On This

- `core/agent.py` (`RentalResearchAgent`) — the only caller. Gets connectors
  exclusively through `ConnectorFactory.get(platform)`, never imports or instantiates
  a connector class itself.
- `analyzers/engine.py` — receives `ConnectorResult.listings` (still `RawListing`
  objects, unchanged shape) via `process_listings()`, exactly as it always has.
- `src/knowledge/knowledge_service.py` — `ConnectorResult`'s
  `results_count`/`response_time_ms`/`success` replace the ad hoc per-platform metrics
  dict `core/agent.py` used to build by hand in v2.0 Step 4; `BaseConnector.health_check()`
  reads back `knowledge_service.connector_health()`, so the SDK and the Knowledge
  Engine share one `ConnectorHealth` model, not two competing ones.
- **Not** `discovery/`: `DiscoveryAgent`/`platform_registry` are unchanged by this
  sprint. Automatic platform discovery/registration from the SDK's `ConnectorRegistry`
  is explicitly out of scope here — see "Deliberately Not Built" below.

## How This Reduces Duplication

Before: every connector's `search()` method independently called `BrowserCollector`,
`raw_page_store.save_page`, and its own parsing loop. After: `BaseConnector.search()`
is a template method implemented exactly once. A new connector implements four small,
genuinely platform-specific hooks:

| Hook | What it does | Genuinely platform-specific? |
|---|---|---|
| `build_url(request)` | Turn a `SearchRequest` into this platform's query URL | Yes — every platform's URL/query shape differs |
| `parse(raw_response)` | Extract a list of platform-native listing records from the raw response | Yes — HTML selectors, JSON keys, XML paths all differ |
| `normalize(raw_record)` | Turn ONE raw record into ONE `RawListing` | Yes — field names/locations differ per platform |
| `connector_info()` | Return this connector's `ConnectorMetadata` | Yes — every platform's coverage/capabilities differ |

Everything else — fetching (`fetch_listing`/`_collect`), raw-page persistence,
validation, capability discovery, health reporting, structured error handling,
self-registration — is inherited. `demo_platform.py`/`demo_platform_two.py` went from
~75 lines each (with real duplication in the `search()` method) to four short methods
apiece with zero duplication between them.

## How This Supports Future APIs and Non-HTML Sources

Transport is a single, overridable seam: `BaseConnector._collect(url) -> str` defaults
to `BrowserCollector` (Playwright). A connector for a platform with a real HTTP API
overrides only `_collect()`:

```python
def _collect(self, url: str) -> str:
    from src.collectors import http_collector
    return http_collector.fetch_text(url)
```

`build_url`/`parse`/`normalize` don't change based on transport — `parse()` for a JSON
API returns a list of dicts instead of BeautifulSoup `Tag`s, and `normalize()` reads
dict keys instead of calling `.select_one()`, but the *sequence* (`fetch_listing ->
parse -> normalize -> validate`) is identical. A future GraphQL, RSS, or CSV source
means the same two changes: override `_collect()` (or `fetch_listing()` entirely, if
the fetch itself isn't a single URL — e.g. paginated requests joined into one
response) and write `parse`/`normalize` for that format. Nothing in `core/agent.py`,
`analyzers/`, `ranking/`, `search_memory/`, or `knowledge/` needs to know any of this
happened — they only ever see `ConnectorResult.listings: list[RawListing]`.

## Architecture

```
src/connectors/
  base.py                    # RawListing only (v2.0 Step 5: Connector ABC removed,
                              #  replaced by BaseConnector below — see that module's
                              #  docstring)
  sdk/
    __init__.py               # public API re-exports
    exceptions.py             # ConnectorException hierarchy
    metadata.py               # ConnectorMetadata, ConnectorCapabilities
    configuration.py          # ConnectorConfiguration
    result.py                 # ConnectorResult
    validator.py              # ConnectorValidator, ValidationResult, ValidationWarning
    registry.py                # ConnectorRegistry, register_connector decorator
    factory.py                 # ConnectorFactory
    base_connector.py           # BaseConnector — the template method
  demo_platform.py            # reference connector, rebuilt on BaseConnector
  demo_platform_two.py        # reference connector, rebuilt on BaseConnector
```

**`ConnectorHealth` is deliberately not defined in `sdk/`.** It already exists as
`src.knowledge.models.ConnectorHealth` (v2.0 Step 4) — successes, failures, average
runtime, last success/failure are exactly what the Knowledge Engine already tracks per
platform. `sdk/__init__.py` re-exports it for discoverability; `BaseConnector.health_check()`
calls `knowledge_service.connector_health(conn, platform_id=self.platform_id)`. One
class, one source of truth, not two definitions of the same concept.

## Lifecycle

```
RentalResearchAgent.run()
  → ConnectorFactory.get(platform)          # never construct a connector directly
      → ConnectorRegistry.get(connector_name)
          → imports src.connectors.<connector_name> if not already loaded
          → the module's @register_connector decorator runs at import time
      → connector_class(config)
  → connector.search(request)                # the template method, below
```

`BaseConnector.search(request: SearchRequest) -> ConnectorResult`:

```
connect()
  → fetch_listing(request)                   # default: build_url() → _collect(url)
                                                #  → raw_page_store.save_page(...)
  → parse(raw_response)                       # platform-specific: list of raw records
  → normalize(raw_record) for each record      # platform-specific: RawListing per record
  → validate(listings)                         # ConnectorValidator — structured warnings
  → (strict_validation, if enabled: raise ConnectorValidationError on any invalid listing)
  → return ConnectorResult(success=True, listings=[...], response_time_ms=..., ...)
finally: disconnect()

On any exception: caught, wrapped if not already a ConnectorException, returned as
ConnectorResult(success=False, listings=[], error="...") — search() never raises.
```

`core/agent.py` reads `result.success`/`result.listings`/`result.error`/
`result.response_time_ms` uniformly; it never needs a `try/except` around fetch/parse
logic itself, only around `ConnectorFactory.get()` (which *can* raise
`ConnectorConfigurationError` before a connector even exists to search with).

## How to Build a New Connector

1. Create `src/connectors/<platform_id>.py`.
2. Subclass `BaseConnector`, set `platform_id = "<platform_id>"`, and decorate the
   class with `@register_connector`.
3. Implement `build_url(request)`, `parse(raw_response)`, `normalize(raw_record)`, and
   `connector_info()`. If the platform needs HTTP instead of a browser, also override
   `_collect(url)`.
4. Register the platform in `discovery/platform_registry.py` with
   `connector_name="<platform_id>"` and `connector_available=True` (see
   [05_Platform_Discovery.md](05_Platform_Discovery.md)) — this is what makes
   `ConnectorFactory.get(platform)` resolvable for it.
5. Write a test file: at minimum, mix in `tests/connectors/sdk/certification.py`'s
   `ConnectorCertificationMixin` (see "Certification Requirements" below) plus any
   parsing-specific assertions for this platform's fixture/fields.
6. Log platform-specific findings (rate limits, auth, page structure) per
   [06_Connector_Framework.md](06_Connector_Framework.md) "Adding a New Connector".

That's the entire list — no change to `core/agent.py`, `ConnectorFactory`, or
`ConnectorRegistry` is ever required for a new platform.

## Best Practices

- **Only `build_url`/`parse`/`normalize`/`connector_info` should know anything about
  the platform.** If you find yourself importing `requests`/`playwright` directly in
  `parse()` or `normalize()`, that logic belongs in `_collect()` (or `fetch_listing()`)
  instead — see [01_System_Architecture.md](01_System_Architecture.md) "The
  Independence Guardrail."
- **`parse()` returns platform-native records; `normalize()` shapes exactly one.** Keep
  the split even when it's tempting to build `RawListing` objects inline inside
  `parse()`'s loop — the separation is what makes `normalize()` independently testable
  and keeps `parse()`'s job legible as "which records exist," not "how to read them."
- **Don't override `search()`.** If a hook's default doesn't fit, override that one
  hook (`_collect()` for transport, `fetch_listing()` for a genuinely different fetch
  shape) — overriding the whole template method reintroduces the duplication this SDK
  exists to remove.
- **Raise the SDK's structured exceptions, not bare ones**, when a hook needs to signal
  failure explicitly (e.g. `raise ConnectorParsingError("unexpected page structure")`
  in `parse()`) — `search()` preserves a `ConnectorException` as-is; anything else gets
  wrapped as a generic `ConnectorConnectionError`, losing the more specific signal.
- **Declare capabilities honestly in `connector_info()`.** `supports_coordinates=False`
  (the default) is correct and expected for most connectors — a rollup consumer
  (`ConnectorCapabilities`) treats an undeclared capability as "no," never "unknown,"
  so there's no cost to being conservative and every cost to overclaiming.

## Certification Requirements

Every connector should pass `tests/connectors/sdk/certification.py`'s
`ConnectorCertificationMixin` before being considered done:

- `platform_id` is set.
- The connector is resolvable via `ConnectorRegistry` (i.e. `@register_connector` was
  applied and the module actually got imported by the test).
- `connector_info()` returns a `ConnectorMetadata` with a non-empty `connector_name`
  (matching `platform_id`), `platform_name`, and `version`.
- `supports(...)` answers for every named capability without raising, for any
  capability name — known or not.
- `search(request)` returns a `ConnectorResult` with `success=True` against a real
  fetch (this requires the same `isolated_collectors` test fixture every other
  connector test uses — see `tests/support.py`).
- Every returned listing has a non-empty `platform_listing_id`, `title`, and `url`.

Both reference connectors (`demo_platform`, `demo_platform_two`) pass this
certification suite — see `tests/connectors/test_demo_platform.py`/
`test_demo_platform_two.py`'s `*CertificationTests` classes.

## Error Handling

| Exception | Raised when |
|---|---|
| `ConnectorException` | Base class — catch this to mean "a connector-related failure," regardless of stage |
| `ConnectorConnectionError` | Fetching failed (network error, timeout, non-2xx response) — the default for anything unexpected `search()` catches |
| `ConnectorParsingError` | The response fetched fine but couldn't be parsed into listing records — raise this explicitly from `parse()` |
| `ConnectorValidationError` | A listing failed validation seriously enough to reject the whole search — only raised when `ConnectorConfiguration.strict_validation=True` (default `False`) |
| `ConnectorConfigurationError` | The connector can't be resolved/constructed at all — unknown `connector_name`, `connector_available=False`, missing connector module — raised by `ConnectorFactory`/`ConnectorRegistry`, before `search()` is ever called |

`search()` itself never raises — every failure inside the fetch/parse/validate
sequence becomes `ConnectorResult(success=False, error=str(exc))`. Only
`ConnectorFactory.get()` can raise (a `ConnectorConfigurationError`), since that
happens *before* a connector instance exists to catch its own errors.

## Deliberately Not Built (Out of Scope for v2.0 Step 5)

- **No real rental-platform connectors.** This sprint is the framework; picking a real
  first platform (`notes/Questions.md`) and writing its connector is unchanged, still
  the next real product step.
- **No automatic platform discovery from the registry.** `ConnectorRegistry.all()`
  exists for introspection/tooling, but nothing wires it into `DiscoveryAgent`/
  `platform_registry.py` to auto-register a platform row just because a connector
  module exists on disk — `discovery/` is untouched by this sprint.
- **No pagination/incremental-search implementation.** `ConnectorMetadata.supports_pagination`/
  `supports_incremental_search` are declarable flags for a future connector to set
  truthfully; no connector (including the two reference ones) actually implements
  either yet.

## Related

- [06_Connector_Framework.md](06_Connector_Framework.md) — the v1.0/v1.1 Connector
  contract this SDK replaces, and the original Connector/Collector split (still
  correct and unchanged: `collectors/` remains generic, reusable fetch infrastructure)
- [01_System_Architecture.md](01_System_Architecture.md) — "The Independence
  Guardrail" and "Repository Writes vs. Service Layer"
- [16_Knowledge_Engine.md](16_Knowledge_Engine.md) — `ConnectorHealth`,
  `ConnectorResult`'s relationship to per-platform observations
- [10_Roadmap.md](10_Roadmap.md) — "Version 2.0" Step 5 for the full implementation
  summary
