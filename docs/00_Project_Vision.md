# 00 — Project Vision

Status: Core principles and V1.0 scope confirmed (2026-07-14). Problem statement / who-it's-for still open.

## What This Is

**Rental Intelligence Platform** — not a one-shot scraper. A search doesn't run, print results, and forget them: it's an event that permanently enriches a growing, queryable body of knowledge about the rental market. The second search on the same city should already be smarter than the first, because it can draw on price history, availability trends, and platform knowledge the first search left behind.

**Rental type: residential apartments** (decided 2026-07-13). Vacation/short-term and equipment rentals are out of scope unless revisited. See [../learning/architecture_notes.md](../learning/architecture_notes.md).

## Core Principles

These are non-negotiable constraints on every design decision made in this project — every doc from [01_System_Architecture.md](01_System_Architecture.md) onward is written to satisfy them:

1. **Never lose information from previous searches.** Nothing is overwritten destructively; see the versioning model in [03_Data_Model.md](03_Data_Model.md).
2. **Every search updates permanent databases.** A search is a write operation against the Apartment, Search History, and (indirectly) Knowledge databases — not a read-only, throwaway operation.
3. **Every apartment has historical versions** (price, availability, status) — tracked as an append-only time series, not a field that just gets overwritten on re-scrape.
4. **Every search is reproducible and comparable over time.** A past search's results must still make sense when read later, even after the underlying apartment data has changed — see the "immutable snapshot" design in [03_Data_Model.md](03_Data_Model.md).
5. **All filters are configurable and extensible.** New filter types must be addable without modifying core search logic — see [04_Search_Request.md](04_Search_Request.md).
6. **The architecture must support new countries, cities, rental types, and data sources without major redesign.** Enforced primarily through the Connector contract ([06_Connector_Framework.md](06_Connector_Framework.md)) being platform-agnostic, not through speculative generalization elsewhere — see "Extensibility Without Over-Engineering" in [01_System_Architecture.md](01_System_Architecture.md).
7. **Business logic must remain independent from any individual website.** No module outside `connectors/` may contain platform-specific logic or assumptions. This is a hard boundary — see [06_Connector_Framework.md](06_Connector_Framework.md).

## V1.0 Scope

The following components ship in V1.0 (see [10_Roadmap.md](10_Roadmap.md) for build order):

- Discovery Agent
- Rental Research Agent (top-level orchestrator)
- Platform Registry
- Apartment Database
- Search History Database
- Knowledge Database
- Ranking Engine
- HTML Report Generator
- Configurable Search Request
- Image extraction
- Original listing URLs
- Availability tracking
- Price history

Explicitly deferred to V2+ (see [10_Roadmap.md](10_Roadmap.md)): cross-platform entity resolution (merging the same physical apartment seen on two platforms into one record), automated platform discovery, AI-assisted ranking/summaries, multi-city/country configuration UI, a web UI (`ui/` ships as a CLI in V1).

## Problem Statement

*TBD.* What manual, slow, or error-prone process is this agent replacing? Write this in one paragraph once the use case (who's searching, and why) is confirmed.

## Who It's For

*TBD.* Who runs a search and reads the report — the business owner, a client, an internal team?

## What Success Looks Like

A search for apartments in a given area returns a ranked, explainable HTML report with real listings, images, and original URLs — and running the same search again next month shows what changed (price movement, listings that disappeared, new listings) instead of starting from zero.

## Non-Goals (V1.0)

- Not solving cross-platform apartment de-duplication/merging (V2 — see [07_Analysis_Engine.md](07_Analysis_Engine.md))
- Not building a web UI (CLI only — see [../docs/02_Folder_Guide.md](02_Folder_Guide.md))
- Not supporting rental types other than residential apartments
- Not building automated platform discovery (static registry only — see [05_Platform_Discovery.md](05_Platform_Discovery.md))

## Guiding Principles (process)

- Documentation-first: architecture and data model are written down before code that depends on them is built (see [13_Claude_Guidelines.md](13_Claude_Guidelines.md)).
- Every platform integration goes through the connector interface in [06_Connector_Framework.md](06_Connector_Framework.md) — no one-off scraping code outside that pattern.
- Every new workflow, bug, lesson, API usage note, architecture decision, and prompt improvement gets recorded in the appropriate file under [../learning/](../learning/Project%20Learning.md).

## Related Documents

- [01_System_Architecture.md](01_System_Architecture.md) — how the vision translates into components
- [10_Roadmap.md](10_Roadmap.md) — phased plan toward this vision
