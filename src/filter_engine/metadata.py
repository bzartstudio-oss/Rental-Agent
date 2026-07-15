"""`FilterMetadata` — a filter's static self-description. See
docs/25_Dynamic_Filter_Engine.md "Filter Lifecycle".

Deliberately shaped to match `filter_definitions` (`storage/schema.sql`, migration
0001) column-for-column — that table was designed for exactly this purpose
("Metadata registry for the Dynamic Filter Engine... kept queryable as data") and sat
unused until this sprint. `FilterMetadata` is the in-memory shape;
`storage/filter_definitions_repository.py` persists it into that real table.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FilterMetadata:
    key: str
    display_name: str
    category: str
    value_type: str
    applicable_rental_types: list[str] = field(default_factory=lambda: ["apartment"])
    description: str = ""
    # True for a filter whose mission-specified field doesn't exist anywhere in
    # `Apartment`/`RawListing` yet (e.g. private_bathroom, gender_preference) — see
    # docs/25_Dynamic_Filter_Engine.md "Dormant Filters" for the full list and why
    # each one honestly always passes rather than fabricating a match/exclusion.
    is_dormant: bool = False
