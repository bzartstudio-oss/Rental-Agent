"""Distance-backed built-in filters — read the Deep Analysis Engine's already-computed
proximity scores (`apartment_analysis_metrics`, v2.0 Step 6) rather than recomputing
any distance themselves. See docs/25_Dynamic_Filter_Engine.md "Built-In Filters".

**Honest limitation, stated plainly**: `walking_distance`/`public_transport`'s stored
`metric_value` is a normalized `[0.0, 1.0]` proximity *score* (1.0 = at the reference
point, 0.0 = at or beyond `_MAX_SCORED_DISTANCE_KM`) — not a literal distance in km or
minutes (see `src/analysis/analyzers/walking_distance.py`; the raw km value only ever
exists as a formatted string inside that analyzer's own `evidence` list, not a
structured field anywhere). A "walking distance ≤ 15 minutes" request, taken
literally, isn't something the current schema can answer — these filters instead take
a **minimum acceptable score**, and say so in their own `description()` rather than
implying unit-accurate distance filtering that doesn't exist yet.
"""

from __future__ import annotations

from typing import Any

from src.filter_engine.base_filter import BaseFilter, FilterContext
from src.filter_engine.metadata import FilterMetadata
from src.filter_engine.registry import register_filter
from src.storage import analysis_metrics_repository
from src.storage.models import Apartment


class _AnalysisScoreFilter(BaseFilter):
    """Shared shape for every filter backed by one Deep Analysis Engine metric's
    stored `[0.0, 1.0]` score — mirrors `analysis/analyzers/nearby_amenity.py`'s
    "shared base + a few lines of config per subclass" pattern.
    """

    _metric_name: str

    def validate(self, value: Any) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not (0.0 <= value <= 1.0):
            raise ValueError(f"expected a proximity score between 0.0 and 1.0, got {value!r}")

    def apply(self, apartment: Apartment, value: Any, context: FilterContext) -> bool:
        score = self._latest_score(apartment.id, context)
        if score is None:
            return True  # no evidence yet — never fabricate an exclusion
        return score >= value

    def _latest_score(self, apartment_id: str, context: FilterContext) -> float | None:
        if context.analysis_results is not None:
            result = context.analysis_results.get(apartment_id)
            if result is None:
                return None
            for analyzer_result in result.analyzer_results:
                if analyzer_result.analyzer_name == self._metric_name:
                    return analyzer_result.score
            return None

        if context.conn is not None:
            metrics = analysis_metrics_repository.get_metrics_for_apartment(
                context.conn, apartment_id, metric_name=self._metric_name
            )
            return metrics[-1].metric_value if metrics else None

        return None


class WalkingDistanceFilter(_AnalysisScoreFilter):
    key = "walking_distance"
    _metric_name = "walking_distance"

    def metadata(self) -> FilterMetadata:
        return FilterMetadata(
            key=self.key, display_name="Walking Distance", category="location", value_type="number",
            description=(
                "Minimum acceptable walking-distance proximity score (0.0-1.0) from the "
                "Deep Analysis Engine's walking_distance analyzer — not a literal distance "
                "in minutes/km; see this module's docstring."
            ),
        )


class PublicTransportTimeFilter(_AnalysisScoreFilter):
    key = "public_transport_time"
    _metric_name = "public_transport"

    def metadata(self) -> FilterMetadata:
        return FilterMetadata(
            key=self.key, display_name="Public Transport Time", category="location", value_type="number",
            description=(
                "Minimum acceptable public-transport proximity score (0.0-1.0) from the "
                "Deep Analysis Engine's public_transport analyzer — not a literal travel "
                "time; see this module's docstring."
            ),
        )


class MaximumDistanceFilter(_AnalysisScoreFilter):
    """A general "how close overall" filter — reuses `walking_distance`'s same
    underlying evidence (real coordinates + a curated reference point) rather than
    inventing a third, parallel distance computation for what is, today, the same
    piece of evidence under a more generic mission-requested name.
    """

    key = "maximum_distance"
    _metric_name = "walking_distance"

    def metadata(self) -> FilterMetadata:
        return FilterMetadata(
            key=self.key, display_name="Maximum Distance", category="location", value_type="number",
            description=(
                "Minimum acceptable proximity score (0.0-1.0), reusing the walking_distance "
                "analyzer's evidence — see this module's docstring for why this isn't a "
                "literal distance unit."
            ),
        )


register_filter(WalkingDistanceFilter())
register_filter(PublicTransportTimeFilter())
register_filter(MaximumDistanceFilter())
