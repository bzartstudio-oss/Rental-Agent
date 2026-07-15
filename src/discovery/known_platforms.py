"""Static, hand-maintained platform candidates — what "discovery" means concretely in
v1.1 (see docs/05_Platform_Discovery.md "When Sync Runs"). Fed to
DiscoveryAgent.sync_platforms() by ui/cli.py on every startup.

Two groups:

1. Reference connectors this codebase actually has (connector_available=True) — see
   connectors/demo_platform.py / demo_platform_two.py.
2. Real, well-known rental platforms with no connector yet (connector_available=False).
   Their names and homepage URLs are public, well-known facts — compiling this list made
   no live request to any of these sites. Fields that would require actually visiting a
   site to verify (exact login requirements, precise city coverage) are deliberately left
   conservative or flagged as unverified in `notes`, rather than guessed at with false
   confidence. `last_verified` is set by sync_platforms() when this list is processed,
   not before — it means "we recorded this metadata," not "we confirmed it's still
   accurate on the live site."
"""

from __future__ import annotations

from src.discovery.discovery_agent import PlatformCandidate

REFERENCE_CONNECTORS: list[PlatformCandidate] = [
    PlatformCandidate(
        platform_id="demo_platform",
        name="Demo Platform (reference/demo connector, not a real rental site)",
        country="N/A (local fixture)",
        homepage="local-fixture",
        supported_cities=["Example City"],
        rental_types=["apartment"],
        connector_available=True,
        connector_name="demo_platform",
        discovery_method="manual_seed",
        notes="Reference connector used to prove the pipeline works end-to-end. See connectors/demo_platform.py.",
    ),
    PlatformCandidate(
        platform_id="demo_platform_two",
        name="Demo Platform Two (reference/demo connector, not a real rental site)",
        country="N/A (local fixture)",
        homepage="local-fixture-two",
        supported_cities=["Example City"],
        rental_types=["apartment"],
        connector_available=True,
        connector_name="demo_platform_two",
        discovery_method="manual_seed",
        notes="Second reference connector, deliberately different fixture shape. See connectors/demo_platform_two.py.",
    ),
    PlatformCandidate(
        platform_id="rentcast",
        name="RentCast",
        country="United States",
        homepage="https://www.rentcast.io",
        supported_cities=["Nationwide (United States)"],
        rental_types=["apartment", "house", "condo", "townhouse"],
        requires_login=False,
        connector_available=True,
        connector_name="rentcast",
        discovery_method="manual_seed",
        notes=(
            "v2.0 Step 7 — the first production (real, non-demo) connector. A real "
            "developer-facing REST API (not a scraped website): self-service signup, "
            "an X-Api-Key header, and published Terms of Use permitting this kind of "
            "programmatic access, verified before writing any connector code. See "
            "docs/20_First_Production_Connector.md. Requires a RENTCAST_API_KEY "
            "environment variable (or ConnectorConfiguration.credentials['api_key']) "
            "to actually authenticate — connector_available=True describes SDK "
            "integration, not that a key is already configured."
        ),
    ),
]

KNOWN_UNSUPPORTED_PLATFORMS: list[PlatformCandidate] = [
    PlatformCandidate(
        platform_id="zillow",
        name="Zillow",
        country="United States",
        homepage="https://www.zillow.com",
        supported_cities=["Nationwide"],
        rental_types=["apartment", "house"],
        requires_login=False,
        connector_available=False,
        discovery_method="manual_research",
        notes="requires_login reflects general public knowledge that browsing/search doesn't need an account; not independently verified against the live site.",
    ),
    PlatformCandidate(
        platform_id="apartments_com",
        name="Apartments.com",
        country="United States",
        homepage="https://www.apartments.com",
        supported_cities=["Nationwide"],
        rental_types=["apartment"],
        requires_login=False,
        connector_available=False,
        discovery_method="manual_research",
        notes="requires_login not independently verified against the live site.",
    ),
    PlatformCandidate(
        platform_id="rightmove",
        name="Rightmove",
        country="United Kingdom",
        homepage="https://www.rightmove.co.uk",
        supported_cities=["Nationwide"],
        rental_types=["apartment", "house"],
        requires_login=False,
        connector_available=False,
        discovery_method="manual_research",
        notes="requires_login not independently verified against the live site.",
    ),
    PlatformCandidate(
        platform_id="idealista",
        name="Idealista",
        country="Spain",
        homepage="https://www.idealista.com",
        supported_cities=["Nationwide"],
        rental_types=["apartment", "house", "room"],
        requires_login=False,
        connector_available=False,
        discovery_method="manual_research",
        notes="Also operates in Italy and Portugal; this entry covers the Spain-focused primary site only. requires_login not independently verified.",
    ),
    PlatformCandidate(
        platform_id="fotocasa",
        name="Fotocasa",
        country="Spain",
        homepage="https://www.fotocasa.es",
        supported_cities=["Nationwide"],
        rental_types=["apartment", "house"],
        requires_login=False,
        connector_available=False,
        discovery_method="manual_research",
        notes="requires_login not independently verified against the live site.",
    ),
    PlatformCandidate(
        platform_id="immoscout24",
        name="ImmoScout24",
        country="Germany",
        homepage="https://www.immobilienscout24.de",
        supported_cities=["Nationwide"],
        rental_types=["apartment", "house"],
        requires_login=False,
        connector_available=False,
        discovery_method="manual_research",
        notes="requires_login not independently verified against the live site.",
    ),
]

ALL_KNOWN_PLATFORMS: list[PlatformCandidate] = REFERENCE_CONNECTORS + KNOWN_UNSUPPORTED_PLATFORMS
