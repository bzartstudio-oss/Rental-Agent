# 06 — Connector Framework

Status: V1.0 Connector/Collector split live in code. **v2.0 Connector SDK & Plugin
Framework live as of v2.0 Step 5 (2026-07-15)** — see "Connector SDK" below and the
full writeup in [18_Connector_SDK.md](18_Connector_SDK.md), now the authoritative doc
for how a connector is actually built. This file's Collector layer content (unchanged)
and the historical v1.0/v1.1 narrative below remain accurate.

## Why a Connector Framework

Every rental platform exposes listings differently — some have a public API, most don't and need browser automation. A connector framework means the rest of the pipeline (Analysis Engine, Ranking, Reports) never needs to know which platform a listing came from — it only ever talks to the shared `RawListing`/`Apartment` shapes in [03_Data_Model.md](03_Data_Model.md). This module is where Principle 7 ("business logic must remain independent from any individual website") is enforced — see the guardrail in [01_System_Architecture.md](01_System_Architecture.md).

## Two Layers: Connectors vs. Collectors

V1.0 splits what earlier drafts called "connectors" into two distinct concerns, because otherwise every connector reimplements its own browser-launching and image-downloading code:

- **Connector** (`connectors/<platform_id>.py`) — platform-specific *only*: knows this one site's URL structure, page layout/selectors or API shape, and how to turn `SearchRequest` criteria into that platform's query. Contains zero fetch/browser mechanics of its own.
- **Collector** (`collectors/`) — generic, reusable, platform-agnostic infrastructure that connectors call into:
  - `browser_collector.py` — Playwright/Chromium page fetching (absorbs the existing `src/browser/browser_manager.py`, expanded into a reusable class rather than a one-off test function)
  - `http_collector.py` — plain HTTP requests, for platforms with a usable API
  - `image_collector.py` — downloads listing images to `data/media/`, returns paths for `apartment_images` rows
  - `raw_page_store.py` — persists raw HTML/screenshots to `data/raw_pages/`, returns paths for `raw_captures` rows

A connector calls a collector; a collector never calls a connector. This keeps the reusable fetch/persistence machinery in one place while keeping platform knowledge fully isolated.

## Connector Contract

**Superseded by the Connector SDK (v2.0 Step 5) — see
[18_Connector_SDK.md](18_Connector_SDK.md).** `connectors/base.py` now holds only
`RawListing`; every connector subclasses `src.connectors.sdk.BaseConnector`, whose
`search(request: SearchRequest) -> ConnectorResult` template method is implemented
once and calls out to `build_url`/`parse`/`normalize`/`connector_info` — the only
genuinely platform-specific pieces. The bullet-point contract that used to live here
(a bare `search(criteria) -> list[RawListing]` abstract method) is what got replaced;
kept below, struck through in spirit, for historical context on what changed and why.

`RawListing` is intentionally looser than `Apartment` (it's pre-normalization) but still a shared shape across all connectors, so the Analysis Engine ([07_Analysis_Engine.md](07_Analysis_Engine.md)) has one input contract regardless of platform. This is unchanged by the SDK — `ConnectorResult.listings` is still `list[RawListing]`.

## Image Extraction (Principle: "image extraction")

A connector's `search()` includes image URLs in each `RawListing`. It is the Analysis Engine, not the connector, that decides to call `image_collector.py` to actually download them (see [07_Analysis_Engine.md](07_Analysis_Engine.md)) — this keeps the connector's job strictly to "get data off this website," not "manage local file storage."

## Adding a New Connector

**See [18_Connector_SDK.md](18_Connector_SDK.md) "How to Build a New Connector" for the
current, authoritative steps** (subclass `BaseConnector`, implement four hooks,
`@register_connector`, certification tests). Summary:

1. Create `src/connectors/<platform_id>.py` subclassing `BaseConnector`
2. `_collect()`'s default uses `collectors/browser_collector.py`; override it for
   `collectors/http_collector.py` instead — don't hand-roll fetch logic in the connector
3. Register the platform in `discovery/platform_registry.py` (see [05_Platform_Discovery.md](05_Platform_Discovery.md))
4. Add a test in `tests/connectors/test_<platform_id>.py`, mixing in the SDK's
   certification suite (`tests/connectors/sdk/certification.py`)
5. Log platform-specific findings (rate limits, auth, page structure) in [../notes/Research.md](../notes/Research.md) first, then durable lessons in [../learning/playwright_notes.md](../learning/playwright_notes.md) or a new topic file if warranted

## Existing Connectors (2026-07-14)

- **`demo_platform.py`** and **`demo_platform_two.py`** — real connectors (real Playwright fetch, real BeautifulSoup parsing) against local HTML fixtures, not live commercial sites. Built to prove the whole framework end-to-end while the actual first platform target was still an open product decision — see [10_Roadmap.md](10_Roadmap.md) "Reference Connector Strategy". Not real rental platforms; each module's own docstring says so.

No real-platform connector exists yet. Adding one is the next real piece of work, following the same steps below.

## Error Handling & Rate Limiting

Every connector must fail gracefully — a broken platform must not crash the whole `RentalResearchAgent` run. **Resolved (2026-07-14):** `core/agent.py` catches any exception from a connector's `search()` call and skips that platform, continuing with whatever other platforms returned — see the next section, which used to be an open question here.

**Partially resolved (v2.0 Step 7):** no single retry/backoff policy is enforced by the SDK itself (`ConnectorConfiguration.max_retries` defaults to `0` — opt-in per connector, not a universal default), but `connectors/rentcast/client.py` establishes a concrete real-world precedent a future connector can follow: exponential backoff for transient failures (connection errors, timeouts, 5xx responses), immediate non-retried failure for anything a retry can't fix (401, and other 4xx). Still genuinely open: whether a *shared* retry helper belongs in `collectors/`/`sdk/` once a second connector needs the same policy, or whether per-connector transport policy (as RentCast has it) is the right long-term shape. Rate limits / robots.txt for scraped (non-API) sites remains unaddressed — no scraped-site connector exists yet to inform that policy.

## Resolved: Connector Failure Handling

Continue with partial results rather than aborting the whole `SearchRequest` — Principle 1 ("never lose information") argues against discarding whatever platforms *did* succeed. Proven in `tests/core/test_agent.py::test_a_broken_connector_does_not_crash_the_whole_run`, which registers a platform pointing at a nonexistent connector module alongside a working one and confirms the working platform's results still come through.

## Connector SDK (v2.0 Step 5, live — full detail in [18_Connector_SDK.md](18_Connector_SDK.md))

The problem this solves is exactly what was sketched here on 2026-07-14: `demo_platform.py`/
`demo_platform_two.py` each independently implemented the same fetch -> save -> parse
sequence — boilerplate, not platform-specific logic. What actually got built in Step 5
is considerably more than this original sketch planned, because the mission's own scope
grew in the meantime (a full Factory/Registry/plugin framework, not just a template
method): `src/connectors/sdk/` now holds `BaseConnector`, `ConnectorFactory`,
`ConnectorRegistry`, `ConnectorMetadata`, `ConnectorCapabilities`, `ConnectorResult`,
`ConnectorValidator`, `ConnectorConfiguration`, and a `ConnectorException` hierarchy.

Two differences from this original sketch, both changed for good reason:

- **`build_url`/`parse` split into `build_url`/`parse`/`normalize`** (three hooks, not
  two) — `parse()` now returns platform-native records (BeautifulSoup elements, JSON
  entries, ...) and `normalize()` shapes exactly one into a `RawListing`. This is what
  actually makes "future APIs and non-HTML sources" (the mission's explicit ask) clean:
  a JSON/XML/CSV connector's `parse()` just returns a different kind of list, and
  `normalize()` is the only method that changes shape.
- **The static `_text`/`_number`/`_attr` extraction helpers sketched here were not
  built.** The `parse`/`normalize` split above already removes the actual duplication
  between the two reference connectors; a shared BeautifulSoup-specific helper module
  would only serve HTML connectors specifically and wasn't needed to eliminate real
  duplication — can be added later if a third HTML-based connector shows the same
  selector-handling pattern repeating.

**What stays exactly the same:** the Collector layer (`browser_collector.py`,
`http_collector.py`, `image_collector.py`, `raw_page_store.py`) is unchanged — the SDK's
default `BaseConnector._collect()` calls `BrowserCollector` exactly as before, just from
inside the base class instead of from each connector module. The old `Connector` ABC
(kept as a possible alias in this sketch) was instead removed outright in the actual
implementation — nothing needed it once `core/agent.py` was updated to use
`ConnectorFactory` instead of a `module.CONNECTOR` attribute lookup. See
[18_Connector_SDK.md](18_Connector_SDK.md) for the complete architecture, lifecycle,
and how-to-build-a-new-connector guide.

## Image Management (v2.0, designed — not yet implemented)

A connector's role is unchanged: report each listing's image URLs in `RawListing.image_urls`,
same as v1.0/v1.1. What's new lives downstream, in the Analysis Engine, not here — see
[07_Analysis_Engine.md](07_Analysis_Engine.md) "Image Change Detection" for how the
system now notices when a re-observed apartment's image set has changed (new photos
added, old ones removed) instead of only handling images at first-discovery time.
