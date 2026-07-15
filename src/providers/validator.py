"""`ProviderValidator` — validates provider-level concerns, deliberately distinct from
`src.connectors.sdk.validator.ConnectorValidator` (which validates *listing* fields
and already runs inside every `BaseConnector.search()` call). Re-validating listings
here would be exactly the duplicated logic the mission's non-functional requirements
forbid — instead, this validator checks the one thing only a provider can be wrong
about: its own declared `ProviderMetadata`, and it surfaces (never re-derives) a data
provider's already-computed `ConnectorResult.validation_warnings`. See
docs/24_Production_Providers.md "Provider Health".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.connectors.sdk.result import ConnectorResult
from src.providers.base import Provider
from src.providers.exceptions import ProviderValidationError
from src.providers.scoring import ProviderMetadata

_SCORE_FIELDS = ("cost_score", "freshness_score", "quality_score")


@dataclass
class ProviderValidationResult:
    provider_id: str
    is_valid: bool
    warnings: list[str] = field(default_factory=list)


class ProviderValidator:
    @staticmethod
    def validate_metadata(metadata: ProviderMetadata) -> list[str]:
        """Every score `score_provider()` (`src.providers.scoring`) consumes is
        documented as `[0, 1]` but never enforced at the point a provider declares
        it — this is that enforcement, run once per validation rather than trusted
        silently.
        """
        warnings = []
        for name in _SCORE_FIELDS:
            value = getattr(metadata, name)
            if not (0.0 <= value <= 1.0):
                warnings.append(f"{name}={value!r} is outside the documented [0, 1] range")
        return warnings

    @staticmethod
    def validate_result(result: ConnectorResult) -> list[str]:
        """Surfaces a data provider's underlying `ConnectorResult.validation_warnings`
        — produced by `ConnectorValidator` inside `BaseConnector.search()` — rather
        than re-checking `RawListing` fields a second time.
        """
        return [f"{warning.field}: {warning.message}" for warning in result.validation_warnings]

    @classmethod
    def validate(
        cls,
        provider: Provider,
        result: ConnectorResult | None = None,
        *,
        strict: bool = False,
    ) -> ProviderValidationResult:
        """`result` is optional: pass a `DataProvider`'s `ConnectorResult` to also
        surface its listing-level warnings; omit it (e.g. for an `AIProvider`, which
        has no `ConnectorResult`) to validate metadata alone. `strict=True` raises
        `ProviderValidationError` instead of just returning `is_valid=False` — off by
        default, mirroring `ConnectorConfiguration.strict_validation`'s same
        opt-in-only reasoning: no existing provider has ever needed outright rejection.
        """
        warnings = cls.validate_metadata(provider.metadata())
        if result is not None:
            warnings.extend(cls.validate_result(result))

        is_valid = not warnings
        if strict and not is_valid:
            raise ProviderValidationError(f"{provider.provider_id}: {'; '.join(warnings)}")

        return ProviderValidationResult(provider_id=provider.provider_id, is_valid=is_valid, warnings=warnings)
