# 05 — Platform Discovery

Status: V1.0 design confirmed (2026-07-14) — static registry, backed by the `platforms` table.

## Goal

Given a `SearchRequest`, decide which `Platform`s (see [03_Data_Model.md](03_Data_Model.md)) are worth querying, then hand that list to the Connector Framework ([06_Connector_Framework.md](06_Connector_Framework.md)).

## Design

Two modules, deliberately separate (see [02_Folder_Guide.md](02_Folder_Guide.md)):

- **`discovery/platform_registry.py`** — the repository layer for the `platforms` table: list active platforms, look one up by ID, register a new one. Pure data access, no decision logic.
- **`discovery/discovery_agent.py`** — the `DiscoveryAgent` class: given a `SearchRequest`, returns the subset of registered platforms relevant to it. In V1.0 this is close to "all active platforms," since location-based platform filtering isn't needed until platforms are country/region-specific — but the seam exists now so that filtering can be added later without touching callers.

## Strategy: Static Registry (V1.0 decision)

Decided over automated discovery (searching the web for "rentals in X" to find new platforms) for V1.0: a static, manually-maintained registry is the fastest path to a working end-to-end pipeline, and automated discovery introduces its own hard problem (trust/quality filtering of a dynamically-found site before ever building a connector for it) that isn't worth solving before the first connector even exists. Automated discovery is a plausible V2 addition layered on top of the same `platforms` table — it would just be a second way of populating it, not a different consumer-facing interface.

## Registering a Platform (V1.0 process)

Manual, via `discovery/platform_registry.py`'s registration function or a direct `INSERT` during setup:

1. Choose a stable `id` slug.
2. Confirm the connector module exists (or is planned) at `connectors.<id>`.
3. Insert into `platforms` with `is_active = 1`.

No admin UI in V1 — `ui/` is CLI-only (see [02_Folder_Guide.md](02_Folder_Guide.md)).

## Open Questions

- Should `DiscoveryAgent` filtering ever be based on something other than "is_active" in V1 (e.g. matching a platform's known coverage area to the request's location)? Deferred until there are ≥2 platforms with genuinely different coverage — no evidence yet this is needed.
- Which platform is the first connector target — see [../notes/Questions.md](../notes/Questions.md).
