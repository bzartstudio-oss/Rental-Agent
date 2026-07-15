"""Unit tests for ProviderRouter — ranking and fallback logic, using small scripted
fake providers (the same "fake connector" strategy
tests/connectors/sdk/test_base_connector.py already uses for BaseConnector's own
orchestration tests) rather than any of the real built-in providers. Every test uses a
private `_FakeRegistry` subclass so nothing here touches the real, shared
`ProviderRegistry`.
"""

from __future__ import annotations

import unittest

from src.providers.base import Provider, ProviderKind
from src.providers.exceptions import NoProviderAvailableError
from src.providers.registry import ProviderRegistry
from src.providers.router import ProviderRouter
from src.providers.scoring import ProviderMetadata, ScoringWeights


class _FakeRegistry(ProviderRegistry):
    _providers: dict = {}


class _ScriptedProvider(Provider):
    """A provider whose availability, score, and `search()`-equivalent outcome are all
    fixed at construction time — enough to script any ranking/fallback scenario
    without needing a real connector or real HTTP call.
    """

    kind = ProviderKind.DATA

    def __init__(self, provider_id: str, available: bool, quality: float, raises: Exception | None = None, returns=None):
        self.provider_id = provider_id
        self._available = available
        self._quality = quality
        self._raises = raises
        self._returns = returns
        self.call_count = 0

    def is_available(self) -> bool:
        return self._available

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider_id=self.provider_id, cost_score=0.0, freshness_score=0.0, quality_score=self._quality)

    def attempt(self):
        self.call_count += 1
        if self._raises is not None:
            raise self._raises
        return self._returns


class RankedCandidatesTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeRegistry.reset()

    def test_unavailable_providers_are_excluded_entirely(self) -> None:
        _FakeRegistry.register(_ScriptedProvider("unavailable", available=False, quality=1.0))
        _FakeRegistry.register(_ScriptedProvider("available", available=True, quality=0.1))

        router = ProviderRouter(ProviderKind.DATA, registry=_FakeRegistry)
        ranked = router.ranked_candidates()

        self.assertEqual([p.provider_id for p, _ in ranked], ["available"])

    def test_higher_quality_ranks_first(self) -> None:
        _FakeRegistry.register(_ScriptedProvider("low", available=True, quality=0.2))
        _FakeRegistry.register(_ScriptedProvider("high", available=True, quality=0.9))

        router = ProviderRouter(ProviderKind.DATA, registry=_FakeRegistry, weights=ScoringWeights(availability=0.0, cost=0.0, freshness=0.0, quality=1.0))
        ranked = router.ranked_candidates()

        self.assertEqual([p.provider_id for p, _ in ranked], ["high", "low"])

    def test_no_registered_providers_of_this_kind_yields_empty_candidates(self) -> None:
        router = ProviderRouter(ProviderKind.AI, registry=_FakeRegistry)
        self.assertEqual(router.ranked_candidates(), [])


class RunWithFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeRegistry.reset()

    def test_selects_the_highest_scored_available_provider_when_it_succeeds(self) -> None:
        high = _ScriptedProvider("high", available=True, quality=0.9, returns="high-result")
        low = _ScriptedProvider("low", available=True, quality=0.1, returns="low-result")
        _FakeRegistry.register(high)
        _FakeRegistry.register(low)
        router = ProviderRouter(ProviderKind.DATA, registry=_FakeRegistry)

        outcome = router.run_with_fallback(lambda provider: provider.attempt())

        self.assertEqual(outcome.provider_id, "high")
        self.assertEqual(outcome.result, "high-result")
        self.assertEqual(high.call_count, 1)
        self.assertEqual(low.call_count, 0)  # never tried — the first candidate succeeded

    def test_falls_back_to_next_provider_when_the_first_raises(self) -> None:
        high = _ScriptedProvider("high", available=True, quality=0.9, raises=RuntimeError("boom"))
        low = _ScriptedProvider("low", available=True, quality=0.1, returns="low-result")
        _FakeRegistry.register(high)
        _FakeRegistry.register(low)
        router = ProviderRouter(ProviderKind.DATA, registry=_FakeRegistry)

        outcome = router.run_with_fallback(lambda provider: provider.attempt())

        self.assertEqual(outcome.provider_id, "low")
        self.assertEqual(outcome.result, "low-result")
        self.assertEqual(high.call_count, 1)
        self.assertEqual(low.call_count, 1)
        self.assertEqual(len(outcome.attempts), 2)
        self.assertFalse(outcome.attempts[0].succeeded)
        self.assertTrue(outcome.attempts[1].succeeded)

    def test_falls_back_to_next_provider_when_is_success_reports_failure(self) -> None:
        """Covers the "returned a failed result, not an exception" case — e.g. a data
        provider's ConnectorResult(success=False, ...), which is exactly how a real
        RentCastDataProvider call that gets rejected (403, timeout, ...) looks.
        """
        high = _ScriptedProvider("high", available=True, quality=0.9, returns={"success": False})
        low = _ScriptedProvider("low", available=True, quality=0.1, returns={"success": True})
        _FakeRegistry.register(high)
        _FakeRegistry.register(low)
        router = ProviderRouter(ProviderKind.DATA, registry=_FakeRegistry)

        outcome = router.run_with_fallback(
            lambda provider: provider.attempt(),
            is_success=lambda result: result["success"],
        )

        self.assertEqual(outcome.provider_id, "low")

    def test_raises_no_provider_available_when_every_candidate_fails(self) -> None:
        a = _ScriptedProvider("a", available=True, quality=0.9, raises=RuntimeError("a failed"))
        b = _ScriptedProvider("b", available=True, quality=0.1, raises=RuntimeError("b failed"))
        _FakeRegistry.register(a)
        _FakeRegistry.register(b)
        router = ProviderRouter(ProviderKind.DATA, registry=_FakeRegistry)

        with self.assertRaises(NoProviderAvailableError):
            router.run_with_fallback(lambda provider: provider.attempt())

        self.assertEqual(a.call_count, 1)
        self.assertEqual(b.call_count, 1)

    def test_raises_no_provider_available_when_nothing_is_available(self) -> None:
        _FakeRegistry.register(_ScriptedProvider("x", available=False, quality=1.0))
        router = ProviderRouter(ProviderKind.DATA, registry=_FakeRegistry)

        with self.assertRaises(NoProviderAvailableError):
            router.run_with_fallback(lambda provider: provider.attempt())

    def test_default_is_success_treats_any_non_raising_result_as_success(self) -> None:
        only = _ScriptedProvider("only", available=True, quality=0.5, returns=None)
        _FakeRegistry.register(only)
        router = ProviderRouter(ProviderKind.DATA, registry=_FakeRegistry)

        outcome = router.run_with_fallback(lambda provider: provider.attempt())

        self.assertEqual(outcome.provider_id, "only")
        self.assertIsNone(outcome.result)


if __name__ == "__main__":
    unittest.main()
