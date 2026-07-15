"""Validates normalized listings before a connector returns them — see
docs/18_Connector_SDK.md "Validation". Every connector gets this for free via
`BaseConnector.validate()`; no connector subclass needs to re-implement field checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.connectors.base import RawListing

# The fields RawListing itself requires (no dataclass default) — see connectors/base.py.
# Checked for presence/non-blankness here too because a connector can still hand back a
# technically-constructed RawListing with an empty string in one of them.
REQUIRED_FIELDS = ("platform_listing_id", "title", "price", "url")


@dataclass
class ValidationWarning:
    field: str
    message: str


@dataclass
class ValidationResult:
    listing: RawListing
    is_valid: bool
    warnings: list[ValidationWarning] = field(default_factory=list)


class ConnectorValidator:
    """Structured, "missing required fields become warnings, not silent data loss"
    validation — not a hard gate by default (see `ConnectorConfiguration.strict_validation`
    for the opt-in exception).
    """

    @staticmethod
    def validate(listing: RawListing) -> ValidationResult:
        warnings = [
            ValidationWarning(field=field_name, message=f"{field_name!r} is missing or empty")
            for field_name in REQUIRED_FIELDS
            if not ConnectorValidator._is_present(getattr(listing, field_name))
        ]
        return ValidationResult(listing=listing, is_valid=not warnings, warnings=warnings)

    @staticmethod
    def validate_all(listings: list[RawListing]) -> list[ValidationResult]:
        return [ConnectorValidator.validate(listing) for listing in listings]

    @staticmethod
    def _is_present(value) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return True
