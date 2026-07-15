"""`ProviderRouter` — selects the best *available* provider of one kind and, if it
fails, tries the next-best one instead of giving up. See
docs/21_Provider_Abstraction_Layer.md "Router & Fallback".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar

from src.providers.base import Provider, ProviderKind
from src.providers.exceptions import NoProviderAvailableError
from src.providers.registry import ProviderRegistry
from src.providers.scoring import DEFAULT_WEIGHTS, ProviderScore, ScoringWeights, score_provider
from src.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class ProviderAttempt:
    """One entry in a `ProviderRunOutcome.attempts` trail — every provider the router
    tried (or skipped as unavailable), in ranked order, with why it did or didn't work.
    """

    provider_id: str
    score: float
    succeeded: bool
    error: str | None = None


@dataclass(frozen=True)
class ProviderRunOutcome(Generic[T]):
    """The result of `ProviderRouter.run_with_fallback()`: which provider ultimately
    produced the result, the result itself, and the full attempt trail — so a caller
    (or a test) can confirm *which* provider was actually used and *why* the others,
    if any, were skipped or failed.
    """

    provider_id: str
    result: T
    attempts: list[ProviderAttempt]


class ProviderRouter:
    """One router per `ProviderKind` — construct `ProviderRouter(ProviderKind.DATA)`
    for the data-provider chain, `ProviderRouter(ProviderKind.AI)` for the AI-provider
    chain. Never hardcodes which providers exist: candidates always come from whatever
    is currently registered in `ProviderRegistry` for this router's `kind`.
    """

    def __init__(
        self,
        kind: ProviderKind,
        weights: ScoringWeights = DEFAULT_WEIGHTS,
        registry: type[ProviderRegistry] = ProviderRegistry,
    ) -> None:
        self._kind = kind
        self._weights = weights
        self._registry = registry

    def ranked_candidates(self) -> list[tuple[Provider, ProviderScore]]:
        """Every registered provider of this router's kind that reports itself
        available right now, scored and sorted best-first. A provider that isn't
        available is excluded entirely — never scored, never a fallback candidate —
        so it can't "win" on cost/freshness/quality despite being unusable.
        """
        candidates = [
            (provider, score_provider(provider.metadata(), available=True, weights=self._weights))
            for provider in self._registry.all(self._kind)
            if provider.is_available()
        ]
        candidates.sort(key=lambda pair: pair[1].total, reverse=True)
        return candidates

    def run_with_fallback(
        self,
        operation: Callable[[Provider], T],
        is_success: Callable[[T], bool] = lambda result: True,
    ) -> ProviderRunOutcome[T]:
        """Tries every available provider of this router's kind, best-scored first.
        `operation(provider)` is called for each in turn; a provider "fails" either by
        raising or by `operation`'s result failing `is_success` (e.g. a data provider
        returning `ConnectorResult(success=False, ...)` — not an exception, but still
        not usable) — either way, the router logs the failure and tries the next
        candidate rather than stopping. Raises `NoProviderAvailableError` only once
        every available candidate has been tried and none succeeded (or none were
        available to begin with).
        """
        ranked = self.ranked_candidates()
        if not ranked:
            raise NoProviderAvailableError(
                f"no available provider registered for kind={self._kind.value!r}"
            )

        logger.info(
            "provider routing decision",
            extra={
                "kind": self._kind.value,
                "ranked": [
                    {"provider_id": provider.provider_id, "score": round(score.total, 4)}
                    for provider, score in ranked
                ],
            },
        )

        attempts: list[ProviderAttempt] = []
        for provider, score in ranked:
            try:
                result = operation(provider)
            except Exception as exc:  # noqa: BLE001 — deliberately broad: any provider failure is a fallback trigger, not a crash
                attempts.append(ProviderAttempt(provider.provider_id, score.total, False, str(exc)))
                logger.warning(
                    "provider attempt raised, trying next",
                    extra={"kind": self._kind.value, "provider_id": provider.provider_id, "error": str(exc)},
                )
                continue

            if is_success(result):
                attempts.append(ProviderAttempt(provider.provider_id, score.total, True))
                logger.info(
                    "provider selected",
                    extra={
                        "kind": self._kind.value,
                        "provider_id": provider.provider_id,
                        "score": round(score.total, 4),
                        "reason": "highest-scored available provider that succeeded",
                    },
                )
                return ProviderRunOutcome(provider_id=provider.provider_id, result=result, attempts=attempts)

            attempts.append(ProviderAttempt(provider.provider_id, score.total, False, "operation reported failure"))
            logger.warning(
                "provider reported failure, trying next",
                extra={"kind": self._kind.value, "provider_id": provider.provider_id},
            )

        raise NoProviderAvailableError(
            f"every available provider for kind={self._kind.value!r} failed: "
            f"{[a.provider_id for a in attempts]}"
        )
