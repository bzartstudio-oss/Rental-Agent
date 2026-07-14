# 04 — Search Request

Status: V1.0 design confirmed (2026-07-14). Concrete parameter list still open (see bottom).

## Definition

A `SearchRequest` is the single object that captures everything a user wants when they ask the agent to go find rentals. Every stage in [01_System_Architecture.md](01_System_Architecture.md) either consumes it directly or consumes something derived from it. It is serialized verbatim into `search_requests.criteria_json` (see [03_Data_Model.md](03_Data_Model.md)) — this is what makes a search reproducible.

## Design: Configurable and Extensible (Principle 5)

A naive `SearchRequest` as a fixed dataclass with fields like `min_price`, `max_price`, `bedrooms` would violate Principle 5 the moment a new filter type is needed — adding one would mean touching the dataclass, the validation logic, the ranking scorer, *and* every connector's query-building code. Instead:

- `SearchRequest` holds a small set of always-required fields (location, and enough to build a report — see below) plus a `criteria: dict[str, FilterValue]` bag.
- Each entry in `criteria` is validated and interpreted by a **registered filter definition** (`search/criteria.py`), not by `SearchRequest` itself. A filter definition declares: its key (e.g. `"max_price"`), the expected value type/shape, and how it contributes to matching/scoring.
- Adding a new filter type in the future means adding one filter definition and registering it — no changes to `SearchRequest`, connectors, or the ranking engine's core loop. This is what "configurable and extensible" means concretely, and it's the same registry pattern the Ranking Engine's scoring consults (see [08_Ranking_System.md](08_Ranking_System.md)).

```
SearchRequest
  id: str (UUID, assigned on creation)
  created_at: datetime
  label: str | None
  location: LocationCriteria        # required — every rental search needs a place
  criteria: dict[str, Any]           # open bag, validated against the filter registry
```

## Required Parameters

- **Location** — structured enough to pass to Platform Discovery ([05_Platform_Discovery.md](05_Platform_Discovery.md)) and to connectors' query-building. *TBD exact shape: city+region string vs. structured city/region/country fields.*

## Optional Parameters (initial filter registry entries)

Proposed starting set — each becomes one filter definition in `search/criteria.py`:

- `min_price` / `max_price`
- `bedrooms` (exact or minimum)
- `bathrooms` (exact or minimum)
- `min_sqft`
- `move_in_date`

This list is deliberately not exhaustive — the whole point of the registry design is that it doesn't need to be.

## Lifecycle

1. **Submitted** — raw input received via `ui/cli.py`
2. **Validated** — required fields present; every key in `criteria` matches a registered filter definition and passes its value validation. Invalid requests fail here with a clear error, not deep in the pipeline.
3. **Persisted** — written to `search_requests` immediately on validation, before execution, so even a search that crashes mid-run leaves a record it was attempted
4. **Executed** — handed to Platform Discovery
5. **Completed** — `search_results` rows exist for this `search_id`, and a Report exists ([09_Report_System.md](09_Report_System.md))

## Open Questions

- Exact structured shape for `location`.
- How is a request submitted beyond the CLI — is a saved/re-runnable request file needed in V1, or is re-typing the same CLI flags sufficient for "reproducible"? (The database-level reproducibility from Principle 4 doesn't require this — it's a UX question, not an architecture one.)
