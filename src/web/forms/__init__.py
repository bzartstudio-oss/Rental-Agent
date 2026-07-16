"""Form validation — see docs/32_Web_Dashboard.md "Form Lifecycle".

Every form module here turns raw `request.form`/`request.args` data into
clean, validated keyword arguments for `WebServiceFacade` — never a
`SearchRequest`/filter/ranking decision itself (that's the Dynamic Filter
Engine's/Ranking Engine V2's job); this package only rejects malformed input
before it ever reaches the facade.
"""

from __future__ import annotations
