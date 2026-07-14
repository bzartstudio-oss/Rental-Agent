# 06 — Connector Framework

Status: V1.0 design confirmed (2026-07-14) — introduces the Connector/Collector split.

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

`connectors/base.py` defines the interface every connector implements:

- `platform_id: str` — matches this connector's row in the `platforms` table
- `search(criteria: SearchCriteria) -> list[RawListing]` — given normalized criteria derived from a `SearchRequest`, return raw results. Internally, this method uses a Collector to fetch pages/data and parses platform-specific structure into `RawListing` objects — it does not return platform-native shapes.

`RawListing` is intentionally looser than `Apartment` (it's pre-normalization) but still a shared shape across all connectors, so the Analysis Engine ([07_Analysis_Engine.md](07_Analysis_Engine.md)) has one input contract regardless of platform.

## Image Extraction (Principle: "image extraction")

A connector's `search()` includes image URLs in each `RawListing`. It is the Analysis Engine, not the connector, that decides to call `image_collector.py` to actually download them (see [07_Analysis_Engine.md](07_Analysis_Engine.md)) — this keeps the connector's job strictly to "get data off this website," not "manage local file storage."

## Adding a New Connector

1. Create `src/connectors/<platform_id>.py` implementing the contract in `base.py`
2. Use `collectors/browser_collector.py` or `http_collector.py` for actual fetching — don't hand-roll fetch logic in the connector
3. Register the platform in `discovery/platform_registry.py` (see [05_Platform_Discovery.md](05_Platform_Discovery.md))
4. Add a test in `tests/connectors/test_<platform_id>.py`
5. Log platform-specific findings (rate limits, auth, page structure) in [../notes/Research.md](../notes/Research.md) first, then durable lessons in [../learning/playwright_notes.md](../learning/playwright_notes.md) or a new topic file if warranted

## Error Handling & Rate Limiting

Every connector must fail gracefully — a broken platform must not crash the whole `RentalResearchAgent` run (see orchestrator responsibility in [01_System_Architecture.md](01_System_Architecture.md)). *TBD: exact retry/backoff policy* — respect reasonable rate limits / robots.txt for scraped sites regardless.

## Open Questions

- Should a connector failure block the whole `SearchRequest`, or continue with partial results and flag the gap in the Report? *Leaning toward continue-with-partial-results*, since Principle 1 ("never lose information") argues against discarding whatever platforms *did* succeed — to confirm once a second connector exists to actually observe a partial-failure scenario.
