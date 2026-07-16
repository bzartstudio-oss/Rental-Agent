"""Web Dashboard & API (v2.5 Step 16) — see docs/32_Web_Dashboard.md.

Every route (HTML or JSON) calls into `WebServiceFacade` only — this package
never recomputes ranking/filter/monitoring/notification/feedback/discovery
logic itself, and never runs raw SQL. See `facade.py`'s own docstring.
"""

from __future__ import annotations
