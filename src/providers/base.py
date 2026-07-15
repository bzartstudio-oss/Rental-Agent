"""`Provider` — the common contract every data provider and AI provider implements. See
docs/21_Provider_Abstraction_Layer.md. Deliberately thin (three members): `provider_id`,
`is_available()`, `metadata()` — everything kind-specific (what a data provider actually
fetches, what an AI provider actually generates) lives on the two narrower subclasses in
`providers/data/base_data_provider.py`/`providers/ai/base_ai_provider.py`, not here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from src.providers.scoring import ProviderMetadata


class ProviderKind(str, Enum):
    DATA = "data"
    AI = "ai"


class Provider(ABC):
    """`provider_id` is a required class attribute (e.g. `provider_id = "rentcast"`) —
    both this provider's registry key and its identity in every log line/scoring
    explanation. `kind` is set by the narrower base class (`DataProvider`/`AIProvider`),
    never by a concrete provider directly.
    """

    provider_id: str
    kind: ProviderKind

    @abstractmethod
    def is_available(self) -> bool:
        """Cheap, side-effect-free check for "can this provider even be tried right
        now" — e.g. is a required API key/environment variable set, is a local service
        reachable. Must never make the actual data/AI call itself; `ProviderRouter`
        calls this for every registered provider on every routing decision, so it needs
        to stay fast. A provider that's `is_available() == True` can still fail when
        actually used — that's what `ProviderRouter.run_with_fallback()`'s fallback
        loop is for, not this method's job to predict.
        """
        raise NotImplementedError

    @abstractmethod
    def metadata(self) -> ProviderMetadata:
        """This provider's static self-description for scoring — cost/freshness/
        quality. One instance per provider, not computed per call.
        """
        raise NotImplementedError
