# 04 — Search Request

Status: **v2.0 Dynamic Filter Engine designed (2026-07-14) — not yet implemented.** The
v1.1 `SearchRequest` + `search/criteria.py` registry pattern (5 filters: `max_price`,
`min_price`, `min_bedrooms`, `min_bathrooms`, `min_sqft`) stays live in code; this doc
designs how it scales to the full filter taxonomy the mission requires, without a
redesign of `SearchRequest` itself — the v1.1 shape already satisfies the requirement,
it just needs more filters registered, organized so "more filters" doesn't mean "one
enormous file."

## Definition (unchanged from v1.1)

A `SearchRequest` is the single object that captures everything a user wants when they
ask the agent to go find rentals — location, plus an open `criteria: dict` bag validated
against the filter registry. Serialized verbatim into `search_requests.criteria_json` —
see [03_Data_Model.md](03_Data_Model.md).

## Why the v1.1 Design Already Scales

The core claim in v1.1 was: "adding a new filter type means adding one filter definition
and registering it — no changes to `SearchRequest`, connectors, or the ranking engine's
core loop." That claim gets tested for real by this upgrade's ~25-filter example list. It
holds, with one addition: **filters are organized by category into a `search/filters/`
subpackage**, not one `criteria.py` file, so "add a filter" means "add a function to the
relevant category file" (or create a new category file), never "edit an existing,
unrelated filter's code."

```
search/
  search_request.py         # unchanged
  criteria.py                # registry mechanics only: FilterDefinition, register(),
                              # get_filter(), apply_filters(), extract_value/weight —
                              # everything that was here in v1.1 EXCEPT the individual
                              # filter registrations
  filters/
    __init__.py               # imports every category module below, so registration
                                # happens on package import — nothing else needs to
                                # change when a category file is added
    budget.py                  # min_price, max_price  (v1.1, migrated as-is)
    property.py                 # min_bedrooms, min_bathrooms, min_sqft (v1.1, migrated),
                                  # property_type, room_type
    timing.py                    # move_in_date, min_availability_duration
    proximity.py                  # max_walking_minutes, max_transit_minutes,
                                    # nearby_supermarket, nearby_university, nearby_gym,
                                    # nearby_pharmacy, nearby_hospital
    amenity.py                     # private_bathroom, air_conditioning, balcony,
                                     # parking, internet, furniture, pets, smoking
    occupant.py                     # gender, student_only, professionals_only
    score.py                         # safety_score, noise_score, lifestyle_score,
                                       # convenience_score, location_score
```

This is a **refactor, not a rewrite**: the 5 existing filter registrations move file
(from `criteria.py` into `filters/budget.py` and `filters/property.py`) with identical
logic — existing tests for them keep passing unchanged (see
[10_Roadmap.md](10_Roadmap.md) "Migration Plan").

## The Proximity/Score Dependency

`proximity.py` and `score.py` filters (`max_walking_minutes`, `safety_score`, etc.)
`matches()`/`score()` against a value that doesn't exist on `Apartment` itself — it comes
from `apartment_analysis_metrics`, computed by the Deep Analysis Engine (see
[07_Analysis_Engine.md](07_Analysis_Engine.md)). This is why the pipeline order (Analysis
→ Ranking, already established in v1.0) matters more under v2.0 than it did before: a
proximity/score filter is only usable for a `SearchRequest` if the Analysis Engine has
already computed that metric for the candidate apartments *in this same run*. A filter
whose metric hasn't been computed yet should fail closed (exclude the apartment, not
crash) — exact mechanism is a v2.0 implementation detail, not resolved further here.

## The Room/Flatshare Filter Tension

`occupant.py` (`gender`, `student_only`, `professionals_only`) and parts of `amenity.py`
(`private_bathroom` only makes sense for a shared/room listing) describe **flatshare-style
search** — the exact concept explicitly kept out of scope in
[00_Project_Vision.md](00_Project_Vision.md) Non-Goals ("not supporting rental types other
than residential apartments"), and confirmed stale when the old `config/settings.json`
was reviewed (see [../learning/architecture_notes.md](../learning/architecture_notes.md)).

This doc does not resolve that tension — it's a product-scope decision, not an
architecture one. What the architecture *does* do is make the tension harmless either
way: `filter_definitions.applicable_rental_types_json` (see
[03_Data_Model.md](03_Data_Model.md)) tags `occupant.py`/room-specific `amenity.py`
filters as applicable to `room`/`shared` rental types. While the system's active scope
stays apartments-only, those filters are registered (satisfying "future filters must be
addable") but simply never relevant to a real search. If room-type search is ever
explicitly greenlit, the filters already exist — only the rental-type scope decision
changes, not the filter framework.

## `filter_definitions` Is Metadata, Not a Replacement for Code

`03_Data_Model.md`'s `filter_definitions` table records *that* a filter exists — its
category, display name, value type. It is deliberately **not** an attempt to make
matching/scoring logic itself data-driven (e.g. a rule-expression stored as a string and
`eval`'d). Building a full no-code rule engine would be real scope creep beyond what's
asked: the requirement is "addable without changing *existing* code," which the
open/closed registry pattern already satisfies (a new filter is new code in a new
location, never a change to code that's already working) — not "addable with *no* code,"
which would require an entire expression-language interpreter to build and secure safely.

## Required Parameters (unchanged from v1.1)

- **Location** — still a plain string, still an open question on exact structured shape.

## Lifecycle (unchanged from v1.1)

Submitted → Validated → Persisted → Executed → Completed. See v1.1 design, still accurate.

## Open Questions

- Exact structured shape for `location` (carried over, still open).
- Exact fail-closed mechanism when a proximity/score filter references a metric that
  wasn't computed for a given apartment in a given run.
- Whether `min_availability_duration` and other `timing.py` filters need their own
  dedicated apartment field, or can be derived from `current_status` + availability
  history — not resolved here, deferred to implementation.
