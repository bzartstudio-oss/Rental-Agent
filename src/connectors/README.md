# connectors/

Code that knows how to query one specific rental platform and return raw results. Full design spec: [../../docs/06_Connector_Framework.md](../../docs/06_Connector_Framework.md) — read that first, this file just orients you inside the folder.

## Contract

Every connector implements (see `base.py` once it exists):

- `search(criteria) -> list[RawListing]`
- `platform_id` — matches the `Platform.id` registered via `discovery/platform_registry.py` (see [../../docs/05_Platform_Discovery.md](../../docs/05_Platform_Discovery.md))

A connector contains **only** platform-specific logic (URL structure, selectors/API shape, query building). Actual fetching goes through [../collectors/](../collectors) (`browser_collector.py` / `http_collector.py`) — a connector must not hand-roll its own Playwright/HTTP calls. Output goes to [../analyzers/](../analyzers) next, which normalizes raw connector output into the shared `Apartment` shape — a connector should not do that normalization itself.

## Adding a connector

One file per platform: `<platform_id>.py`. Steps are in [../../docs/06_Connector_Framework.md](../../docs/06_Connector_Framework.md#adding-a-new-connector).

## Status

No connectors implemented yet.
