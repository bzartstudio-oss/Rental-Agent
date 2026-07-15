"""`FilterConfiguration` — controls which registered filters actually run, and how
strictly, without touching `FilterEngine` or any filter's own code. See
docs/25_Dynamic_Filter_Engine.md "Filter Lifecycle".

This is the concrete mechanism behind the mission's "added, removed, enabled or
disabled without changing the search engine": disabling a filter is setting
`enabled_filter_keys` to a set that omits it, never an edit to `FilterEngine` or the
filter itself.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FilterConfiguration:
    # `None` (the default) means every registered filter is a candidate — the same
    # nullable-means-"no restriction" convention `ConnectorConfiguration.rate_limit_per_minute`
    # already established. A `set` restricts execution to exactly those keys.
    enabled_filter_keys: set[str] | None = None
    # Mirrors `ConnectorConfiguration.strict_validation`/`ProviderConfiguration`'s own
    # opt-in-only reasoning: off by default, since no built-in filter has ever needed
    # a criterion value rejected outright rather than just excluded from matching.
    strict_validation: bool = False

    def is_enabled(self, key: str) -> bool:
        return self.enabled_filter_keys is None or key in self.enabled_filter_keys
