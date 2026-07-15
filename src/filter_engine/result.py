"""`FilterResult` — the uniform, per-apartment output of running a filter set. See
docs/25_Dynamic_Filter_Engine.md "Filter Pipeline".
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FilterResult:
    """One apartment's outcome against a composed filter set. `per_filter` records
    every individual filter's own True/False (even ones that didn't affect the final
    `matches`, e.g. inside an OR group) — so a caller can explain *why* an apartment
    was kept or excluded, not just the final boolean.
    """

    apartment_id: str
    matches: bool
    per_filter: dict[str, bool] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
