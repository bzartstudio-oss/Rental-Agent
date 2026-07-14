"""SearchRequest — see docs/04_Search_Request.md. The single object that captures
everything a user wants when they ask the agent to search; serialized verbatim into
search_requests.criteria_json (storage/search_repository.py) so the search is reproducible
(docs/00_Project_Vision.md Principle 4).

`location` is a plain string for V1 (docs/04_Search_Request.md leaves the structured
shape as an open question) — simplest choice that unblocks the rest of the pipeline;
revisit if/when connectors need more than a free-text location to build a real query.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.search.criteria import validate_criteria


@dataclass
class SearchRequest:
    location: str
    criteria: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    label: str | None = None

    def __post_init__(self) -> None:
        if not self.location:
            raise ValueError("SearchRequest.location is required")
        validate_criteria(self.criteria)

    def to_criteria_json(self) -> str:
        """The exact serialized form persisted to search_requests.criteria_json."""
        return json.dumps({"location": self.location, "criteria": self.criteria})
