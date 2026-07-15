"""Pure geographic math — no external service, no API key, no network call. This is
deliberately the only kind of "location" computation this sprint implements for real:
given two coordinate pairs, the distance between them is arithmetic, not a vendor
decision. Turning an address into coordinates (geocoding) or finding real nearby
points of interest is NOT implemented here — that requires an actual data source
decision explicitly deferred (docs/07_Analysis_Engine.md "Open Questions",
docs/19_Analysis_Engine.md).
"""

from __future__ import annotations

import math

_EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two (latitude, longitude) points, in kilometers."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))
