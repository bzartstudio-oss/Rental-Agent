"""Every built-in analyzer module, imported here so `@register_analyzer` runs for all
of them the moment this package is imported — see `src.analysis.registry`'s docstring
for why analyzers are imported eagerly rather than lazily (unlike `connectors.sdk`'s
`ConnectorRegistry`, which imports connector modules on demand).

Adding a new analyzer: create the module, add one line here. `AnalysisPipeline`/
`AnalysisEngine` never need to change.
"""

from __future__ import annotations

from src.analysis.analyzers import (  # noqa: F401
    nearby_amenity,
    public_transport,
    walking_distance,
)
