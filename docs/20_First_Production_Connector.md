# 20 — First Production Connector (RentCast)

Status: **Live as of v2.0 Step 7 (2026-07-15)** — see `src/connectors/rentcast/`.

Note on numbering: the mission for this sprint asked for
`docs/19_First_Production_Connector.md`, but `19` was already taken by
[19_Analysis_Engine.md](19_Analysis_Engine.md) (v2.0 Step 6). This is `20` instead —
the same numbering collision Steps 5 and 6 each hit before this one, resolved the same
way both times: next free number, never a renumbering of anything existing.

## Why This Sprint Exists

Every connector built so far (`demo_platform`, `demo_platform_two`) is a fixture — real
code, run through a real browser, against a real local HTML file, but never a real
website. The Connector SDK (v2.0 Step 5) was designed against those two fixtures and
never proven against anything else. This sprint's job is narrow: prove the SDK holds up
against one real, external, uncooperative data source — not to add broad rental-site
coverage. One production connector is the entire scope.

## Why RentCast

This project has carried an explicitly open question since v1.1
([00_Project_Vision.md](00_Project_Vision.md), `notes/Questions.md`, and
[10_Roadmap.md](10_Roadmap.md) "Reference Connector Strategy") over which real rental
platform to integrate first. Six candidates were catalogued along the way — Zillow,
Apartments.com, Rightmove, Idealista, Fotocasa, ImmoScout24 — and all six remain
`connector_available=False` in `discovery/known_platforms.py` for the same reason:
none offers a self-service API, and all publish Terms of Service that prohibit
automated scraping. Building a connector against any of them would mean either
bypassing anti-bot protection (explicitly forbidden by this sprint's mission) or
violating the platform's own published terms — neither is acceptable.

RentCast (<https://www.rentcast.io>) was chosen instead, verified before any connector
code was written (via live fetches of its own developer documentation, not assumed from
training data):

- **A real, developer-facing REST API**, not a scraped website:
  `GET /listings/rental/long-term` at `https://api.rentcast.io/v1`
  ([reference](https://developers.rentcast.io/reference/rental-listings-long-term)),
  plus a single-record `GET /listings/rental/long-term/{id}`
  ([reference](https://developers.rentcast.io/reference/rental-listing-long-term-by-id)).
- **Self-service authentication** — an `X-Api-Key` header, obtained by signing up at
  <https://app.rentcast.io/app/api>. No login flow to automate, no session to maintain,
  no CAPTCHA to solve.
- **A published free tier** (50 requests/month, no credit card required) sufficient to
  build, test, and demonstrate this connector without a paid plan.
- **Published Terms of Use that permit this kind of programmatic access** — this is the
  platform's own supported integration path, not a workaround.
- **Enough listing data to exercise the full pipeline**: price, address, coordinates,
  property type, bedrooms/bathrooms/square footage, and listing status, all real fields
  returned by the real API (see "Supported Fields" below).

No authentication is bypassed, no anti-bot or CAPTCHA protection is circumvented, and
nothing about this connector's traffic differs from what any legitimate developer using
RentCast's own documented API would send.

## Preliminary Questions (from the mission)

**1. Why are production connectors separated from the SDK?** The SDK
(`src/connectors/sdk/`) is the framework — `BaseConnector`'s template method,
`ConnectorFactory`/`ConnectorRegistry`, structured errors/validation/metadata. None of
that is specific to any platform. `RentCastConnector` (this sprint) implements exactly
the same four hooks `DemoPlatformConnector` does (`build_url`/`parse`/`normalize`/
`connector_info`, plus an overridden `connect()`/`fetch_listing()` where RentCast's
transport genuinely differs) — nothing about RentCast's schema, auth, or pagination
ever touches `src/connectors/sdk/`. A platform going away, changing its schema, or
being replaced by another data source never requires touching the framework.

**2. How is connector maintenance isolated?** Every RentCast-specific detail —
its base URL, its query parameters, its JSON schema, its retry/backoff policy — lives
inside `src/connectors/rentcast/` (two files: `connector.py`, `client.py`) and nowhere
else. If RentCast changes its response shape tomorrow, the fix is contained to that one
package; `core/agent.py`, `analyzers/`, `storage/`, `ranking/`, and every other
connector are untouched. This is the same "Independence Guardrail"
([01_System_Architecture.md](01_System_Architecture.md)) `demo_platform.py`/
`demo_platform_two.py` already prove — this sprint proves it holds for a real, external
API too, not just two local fixtures.

**3. How will new connectors be added in the future?** Exactly the process
[18_Connector_SDK.md](18_Connector_SDK.md) already documents, unchanged by this sprint:
create `src/connectors/<name>/`, subclass `BaseConnector`, implement `build_url`/
`parse`/`normalize`/`connector_info` (override `connect()`/`fetch_listing()` too if the
platform's transport isn't a single browser-fetched URL, as RentCast's isn't),
decorate with `@register_connector`, add a `PlatformCandidate` to
`discovery/known_platforms.py`. See "How to Add the Next Connector" below for the
concrete, RentCast-informed version of this checklist.

**4. How does the connector handle failures gracefully?** The same way every
connector does, via `BaseConnector.search()`'s template method — `connect()` is called
*inside* a try/except (see "A Fix Along the Way" below), so a failure at any stage
(missing API key, network timeout, malformed response, a listing with a missing
required field) is caught and returned as a normal `ConnectorResult(success=False,
error=...)`, never a raised exception. `RentCastClient` additionally distinguishes
*which* failures are worth retrying (connection errors, timeouts, 5xx responses — all
transient) from which aren't (a 401, which no amount of retrying fixes) — see
"Retry Policy" below.

## A Fix Along the Way

Building this connector surfaced a real, pre-existing bug in
`BaseConnector.search()` (v2.0 Step 5): `self.connect()` was called *outside* the
`try:` block wrapping the rest of `search()`. This was invisible for the two demo
connectors, whose `connect()` is a no-op that never raises. `RentCastConnector.connect()`
is the first one that legitimately needs to raise (`ConnectorConfigurationError` when no
API key is configured) — with the bug in place, that exception would have propagated
straight out of `search()`, breaking the documented "search() never raises" guarantee
the moment a connector actually needed it. Fixed by moving `connect()` inside the
`try:` block; verified against the full `tests/connectors/` suite (all pre-existing
tests still pass — a strict widening of the guard, no behavior change for connectors
whose `connect()` never raises).

## Architecture

```
src/connectors/rentcast/
  __init__.py     # imports connector.py -> runs @register_connector
  connector.py    # RentCastConnector(BaseConnector) — platform_id = "rentcast"
  client.py       # RentCastClient — HTTP transport, retry/backoff, auth header
  fixtures/
    sample_response.json   # hand-built, schema-accurate example (not a live capture)

src/utils/logging.py   # get_logger()/StructuredFormatter — new in this sprint,
                        # the first module in this codebase to use `logging` at all
```

## Credential Handling

`ConnectorFactory.get(platform)` is called from `core/agent.py` with no per-platform
config — by design, so the Research Agent never needs to know which connector requires
what credential (`docs/01_System_Architecture.md` "No connector-specific code in the
Research Agent" — see "Integration" below). `RentCastConnector.connect()` therefore
resolves its own API key with a two-step fallback:

1. `ConnectorConfiguration(credentials={"api_key": ...})`, if the caller explicitly
   constructed one (the SDK-sanctioned per-instance override — useful for tests or a
   future multi-tenant caller).
2. The `RENTCAST_API_KEY` environment variable, otherwise.

Neither the key's value nor any request header containing it is ever logged — the
structured logger (`src/utils/logging.py`) only ever receives `path`/`attempt`/
`status_code`/`count`, never headers or credentials. The key is never hardcoded, never
committed, and never written to a file that enters git.

## Supported Fields — Mapping Table

| `RawListing` field | RentCast source | Notes |
|---|---|---|
| `platform_listing_id` | `id` | Required; a listing without one fails normalization (see "Failure Modes") |
| `title` | `formattedAddress` (falls back to `id`) | RentCast has no listing title field — the formatted address stands in for one |
| `price` | `price` | Defaults to `0.0` if absent, never crashes |
| `url` | `{BASE_URL}/listings/rental/long-term/{id}` | RentCast's own single-record API endpoint — an API reference, **not** a browsable page a person could open in a browser (see "Limitations") |
| `bedrooms` | `bedrooms` | `None` if absent |
| `bathrooms` | `bathrooms` | `None` if absent |
| `sqft` | `squareFootage` | `None` if absent |
| `address_raw` | `formattedAddress` | `None` if absent |
| `status` | `"available"` if RentCast's `status == "Active"`, else passed through | Matches the existing `RawListing.status` convention (docs/03_Data_Model.md) |
| `latitude` / `longitude` | `latitude` / `longitude` | `None` if absent — RentCast omits these for some listings |
| `currency` | always `"USD"` | RentCast covers US listings only; never fabricated for a non-US platform |
| `property_type` | `propertyType` | `None` if absent |
| `image_urls` | always `[]` | RentCast's schema has no photos field at all — an honest gap, not a bug |
| `description` | always `None` | RentCast's schema has no description field at all — an honest gap, not a bug |

`currency` and `property_type` are new `Apartment`/`RawListing` fields added by this
sprint (migration `0004_production_connector_fields.sql`, both nullable) — no prior
connector had real data for either. `latitude`/`longitude` already existed on
`Apartment` (since migration 0001) but had never been populated by any connector until
now; `normalizer.py` gained the two lines needed to pass them through.

## Retry Policy

`RentCastClient` (not `BaseConnector` — this is transport-layer, not SDK-layer, policy)
retries a connection error, timeout, or 5xx response up to `ConnectorConfiguration.
max_retries` times, with exponential backoff (`0.5s, 1s, 2s, ...`). A 401 (bad/missing
API key) and any other non-5xx error response (400, 403, 404, 429, ...) fail
immediately without retrying — no number of retries turns a bad key or a malformed
request into a good one.

## Pagination

`GET /listings/rental/long-term` supports `limit`/`offset` pagination
(`includeTotalCount` for a total-count header, unused here). This connector paginates
at 100 listings/page, up to 3 pages (`_PAGE_SIZE`/`_MAX_PAGES` in `connector.py`) —
a **deliberately conservative** cap, not RentCast's own maximum: the free tier is 50
requests/month, and a single search must never have the ability to silently exhaust it
in one call. 3 pages × 1 search still leaves headroom for the remaining 47 requests
that month, at up to 300 listings per platform per search.

## Location Parsing

`SearchRequest.location` is a free-text string — its structured shape is still an open
question ([04_Search_Request.md](04_Search_Request.md)). This connector splits on the
first comma into `city`/`state` (`"Austin, TX"` → `city=Austin, state=TX`); a location
with no comma is sent as `city` alone. A known, honest limitation: RentCast's `city`/
`state` params are exact-match, so an unusually formatted location can return zero
results rather than a fuzzy match.

Bedroom/bathroom/square-footage/price criteria (`SearchRequest.criteria`) are
deliberately **not** translated into RentCast query parameters. RentCast's `bedrooms`/
`bathrooms`/`squareFootage` params are exact-match, not minimum thresholds — sending
`min_bedrooms=2` as `bedrooms=2` would incorrectly exclude a matching 3-bedroom listing.
That hard-filtering already happens downstream, generically, for every connector
regardless of platform (`src/search/criteria.py`'s pass, used by `ranking/`) —
duplicating it in this connector would be redundant at best, wrong at worst.

## Limitations

- **No photos.** RentCast's schema has no images field. Every RentCast-sourced
  `Apartment` has `image_urls == []` — a real, honest gap, not a bug to be fixed by a
  future patch to *this* connector (it would require an entirely different data
  source).
- **No description.** Same reasoning; always `None`.
- **No browsable listing page.** `url` points at RentCast's own API record for the
  listing (`GET /listings/rental/long-term/{id}`), not a page a renter could open and
  read. The HTML report still renders it as "Original listing," which for this
  connector means "the API record used to build this entry," documented here so that
  distinction isn't lost.
- **US-only coverage.** RentCast has no international data; `supported_countries =
  ["United States"]` in `connector_info()`.
- **Free-tier quota.** 50 requests/month unless a paid plan is configured — this is why
  pagination is capped conservatively (see "Pagination") and why every test in
  `tests/connectors/rentcast/` mocks the HTTP layer rather than making real calls.
- **Exact-match location/criteria matching.** See "Location Parsing" above.

## Analysis Engine Interaction

[19_Analysis_Engine.md](19_Analysis_Engine.md) "Evidence Model" documented that no
connector had ever populated `Apartment.latitude`/`.longitude`, so the coordinate-based
analyzers (`walking_distance`, `public_transport`) were dormant by construction, not by
a missing feature. That's no longer true for RentCast-sourced apartments: real
coordinates now exist for any listing RentCast reports them for. Those two analyzers
still require a curated reference point in `knowledge_entries`
([19_Analysis_Engine.md](19_Analysis_Engine.md) "Evidence Model") to compute a distance
against — this sprint does not add any such curated data, so they remain dormant for
any location without one. The gap that's closed is coordinates; the gap that remains
open is reference-point curation, unchanged and still explicitly out of scope.

## Integration

`RentCastConnector` is obtained exactly like `DemoPlatformConnector` — via
`ConnectorFactory.get(platform)` in `core/agent.py`, with no RentCast-specific branch
anywhere in that file. It is registered in `discovery/known_platforms.py`'s
`REFERENCE_CONNECTORS` list (`connector_available=True`, `connector_name="rentcast"`),
exactly the same way the two demo connectors are, so `DiscoveryAgent.discover()` picks
it up automatically for every search. `tests/core/test_rentcast_integration.py` proves
the full path — Connector SDK → Research Agent → Apartment History → Search Memory →
Knowledge Engine → Deep Analysis Engine → Ranking → HTML Report — with the HTTP layer
mocked but every other stage genuinely exercised, and confirms zero RentCast-specific
code exists in any of those downstream modules.

## Certification & Tests

- `tests/connectors/rentcast/test_client.py` — `RentCastClient` unit tests: success,
  401 (immediate failure, never retried), 5xx (retried then succeeds / retries
  exhausted then raises), timeout and connection-error retry behavior, non-5xx errors
  (never retried).
- `tests/connectors/rentcast/test_connector.py` — `RentCastConnector` unit tests:
  `connect()`'s credential fallback chain, `build_url()`, `parse()` (passthrough),
  `normalize()` against a fully-populated listing, a listing missing coordinates, a
  sparse listing (only `id`/`status`/`price`), a malformed listing (missing `id`),
  pagination (short page stops early, full pages stop at `_MAX_PAGES`, raw-page
  capture, wrapped connection errors), and `connector_info()`'s declared capabilities.
- `tests/connectors/rentcast/test_search_behavior.py` — full `search()`-level tests:
  successful search, missing images, missing coordinates, empty results, malformed
  listing, network timeout, and missing API key — every one confirmed to return a
  normal `ConnectorResult(success=False, ...)` rather than a raised exception.
- `tests/connectors/rentcast/test_certification.py` — `ConnectorCertificationMixin`
  (the same SDK-wide certification suite every connector is certified with), with a
  mocked HTTP layer and a fake API key so `self.connector_class()` (instantiated with
  no arguments by the mixin itself) can complete a real `search()` call.
- `tests/core/test_rentcast_integration.py` — the full-pipeline proof described under
  "Integration" above.

All new tests mock the HTTP layer (`RentCastClient`/`requests.get`) — no test in this
codebase makes a real network call to RentCast, both for CI reliability and to avoid
spending any of a real free-tier quota.

## Live Verification

Once a real `RENTCAST_API_KEY` is available, one real, live search was run against the
actual RentCast API (not mocked) to confirm the connector works against the live
service end-to-end, exactly as required by this sprint's "Final Verification." The key
was supplied transiently at run time (`RENTCAST_API_KEY` environment variable), never
logged, and never committed.

## How to Add the Next Connector

1. Verify the target platform the same way this sprint verified RentCast: confirm a
   real, self-service, ToS-compliant access path exists (an API, or a scraping-permitted
   site) — via live lookup, never assumed from training data. If no such path exists,
   document that and pick a different source (this sprint's own resolution for the six
   previously-catalogued platforms).
2. Create `src/connectors/<name>/` with at least `connector.py` (subclass
   `BaseConnector`, implement `build_url`/`parse`/`normalize`/`connector_info`) — add a
   `client.py` too if the platform needs its own HTTP/auth logic, following
   `rentcast/client.py`'s shape.
3. Decorate the connector class with `@register_connector`; export it from
   `__init__.py` so `ConnectorRegistry._ensure_imported()` finds it.
4. If the platform needs a credential, resolve it inside `connect()` with the same
   config-then-environment-variable fallback this sprint established — never require
   `core/agent.py` to change.
5. Map every field the platform's schema actually provides into `RawListing`; leave
   anything the platform doesn't provide at its honest default (`None`/`[]`) — never
   fabricate.
6. Add a `PlatformCandidate` to `discovery/known_platforms.py`'s `REFERENCE_CONNECTORS`.
7. Write the same test shape this sprint used: client-level retry/backoff tests,
   connector-level normalize/parse/failure tests, `ConnectorCertificationMixin`
   certification, and one full-pipeline integration test — all against mocked HTTP.
8. Run the complete test suite; update this doc's mapping-table pattern (a new
   `docs/NN_<Name>_Connector.md` or an addition here, whichever the next sprint's
   mission asks for).

## Related

- [18_Connector_SDK.md](18_Connector_SDK.md) — the framework this connector is built on
- [19_Analysis_Engine.md](19_Analysis_Engine.md) — "Evidence Model" section, updated in
  spirit (not rewritten) by this sprint's coordinate data
- [06_Connector_Framework.md](06_Connector_Framework.md) — the original per-platform
  connector concept this SDK generalized
- [03_Data_Model.md](03_Data_Model.md) — `apartments.currency`/`.property_type`
  (migration 0004)
- [10_Roadmap.md](10_Roadmap.md) — "Version 2.0" Step 7 for the full implementation summary
