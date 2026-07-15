# 22 — SDK Validation Sprint

Status: **Done (2026-07-15)**. Not a numbered Version 2.0 step, and not new
functionality — a verification exercise against four specific, testable claims the
Connector SDK (v2.0 Step 5) has made since it was built. Every answer below is backed
by something actually run this sprint (a real added connector, a real test, a real
`git status`), not a restatement of design intent.

## Method

A third reference connector, `SampleJsonFeedConnector`
(`src/connectors/sample_json_feed/`), was added purely as a controlled experiment —
not a real platform, not seeded into `discovery/known_platforms.py`, never meant to be
a real data source. It exists only so this sprint could observe, empirically, whether
adding a connector really requires zero changes elsewhere and really gets discovered
automatically, rather than asserting it from memory of how the SDK was designed.

## Question 1: Can a second connector be added without changing existing code?

**Yes.** Evidence: `git status --short src/connectors/sample_json_feed/
tests/connectors/test_sample_json_feed.py` shows exactly two new, untracked paths —

```
?? src/connectors/sample_json_feed/
?? tests/connectors/test_sample_json_feed.py
```

— and nothing else. `grep -l "sample_json_feed"` against every file this session had
already modified for unrelated reasons (`src/connectors/base.py`,
`src/connectors/sdk/base_connector.py`, `src/discovery/known_platforms.py` — all
touched during v2.0 Step 7's RentCast work, weeks — well, sprints — before this one)
returns zero matches: adding this connector didn't even add a passing reference to
those files, let alone modify them.

One nuance worth being precise about: **registering a `Platform` row in
`discovery/known_platforms.py` is a separate, optional step from the SDK's own
connector-resolution mechanism.** `SampleJsonFeedConnector` is deliberately *not* in
that seed list — every test resolves it by constructing a `Platform` object directly
(`Platform(id=..., connector_name="sample_json_feed", ...)`), exactly the way
`RentCastDataProvider`/`LocalDemoDataProvider` (Provider Abstraction Layer) already do
internally. `known_platforms.py` controls which platforms the *app* seeds into a
running database by default — a product/catalog decision — not whether the *SDK* can
resolve and run a connector. This is the same distinction Step 7 already drew when
`connector_available=True` there meant "SDK-integrated," not "a key is already
configured."

This also confirms, retroactively, that the same held for the two connectors added
before the SDK Validation Sprint was requested: `demo_platform_two.py` (v1.0 Phase 7)
and `src/connectors/rentcast/` (v2.0 Step 7) each required exactly one new
connector package/file plus one new `PlatformCandidate` entry — never a change to
`connectors/sdk/`, `core/agent.py`, `analyzers/`, `ranking/`, or any other connector.

## Question 2: Does the factory discover connectors automatically?

**Yes.** `tests/connectors/test_sample_json_feed.py::AutoDiscoveryTests` proves this
directly, not by inspection of the registry's code: `setUp()` forcibly evicts
`"sample_json_feed"` from `ConnectorRegistry._connectors` and from `sys.modules`,
guaranteeing a genuinely "never imported" starting state regardless of what any other
test in the suite already did. The test then asserts:

```python
self.assertFalse(ConnectorRegistry.is_registered("sample_json_feed"))
...
connector = ConnectorFactory.get(platform)  # platform.connector_name == "sample_json_feed"
self.assertTrue(ConnectorRegistry.is_registered("sample_json_feed"))
```

`False` before, `True` after — with nothing in between except one `ConnectorFactory.get()`
call. Mechanically: `ConnectorRegistry.get(connector_name)` calls
`importlib.import_module(f"src.connectors.{connector_name}")` when the name isn't
already registered; importing that module runs its `@register_connector` decorator as
a side effect. The same test also confirms a genuinely unknown `connector_name`
(`"definitely_not_a_real_connector"`) raises `ConnectorConfigurationError` — not a bare
`ImportError`/`KeyError` — proving the lookup path is real, general-purpose logic, not
a special case written for this one connector's name.

A live, interactive version of the same proof (run this sprint, not just in a test):

```
>>> ConnectorRegistry.is_registered("sample_json_feed")
False
>>> ConnectorFactory.get(platform)   # platform.connector_name == "sample_json_feed"
>>> ConnectorRegistry.is_registered("sample_json_feed")
True
```

## Question 3: Are connectors truly independent?

**Yes**, checked three ways, not just asserted:

**1. Import audit.** Every internal (`from src...`) import in every connector module:

```
demo_platform.py:       connectors.base, connectors.sdk, search.search_request
demo_platform_two.py:   connectors.base, connectors.sdk, search.search_request
rentcast/connector.py:  collectors.raw_page_store, connectors.base, connectors.rentcast.client,
                        connectors.sdk(.*), search.search_request, utils.logging
sample_json_feed/connector.py: connectors.base, connectors.sdk, search.search_request
```

Zero connector imports another connector's module. Zero connector imports from
`analyzers/`, `ranking/`, `knowledge/`, `history/`, `search_memory/`, or `services/` —
only `connectors/` (its own base/SDK), `collectors/` (generic fetch infrastructure),
`search/` (the shared `SearchRequest` input type), and `utils/` (generic logging). This
is [01_System_Architecture.md](01_System_Architecture.md)'s "Independence Guardrail"
("only `connectors/` may import or reference anything platform-specific") holding up
under an actual grep, not just stated as a rule.

**2. Test isolation.** Each connector's own test module runs standalone and passes
with no other connector's tests present:

```
tests.connectors.test_demo_platform        — 12 tests, OK, run alone
tests.connectors.test_demo_platform_two    —  8 tests, OK, run alone
tests.connectors.test_sample_json_feed     — 12 tests, OK, run alone
tests.connectors.rentcast.*                — 47 tests, OK, run alone (all HTTP mocked)
```

None of these imports or depends on another connector's module, fixture, or database
state.

**3. No shared mutable state.** `ConnectorRegistry` is the only thing every connector
touches in common, and it's additive-only (`register()` sets one dict key per
`platform_id`) — one connector's registration can never overwrite or interfere with
another's, and removing a connector module from the codebase entirely would leave
every other connector's behavior completely unaffected (nothing conditions its logic
on which *other* connectors happen to be installed).

## Question 4: Is the normalized apartment model complete enough for different platforms?

**Mostly — two genuine gaps found and left open, one gap found and fixed this
sprint.** Four structurally different sources now exercise the same `RawListing`/
`Apartment` shape: two HTML fixtures (`demo_platform`, `demo_platform_two`), one real
external HTTP JSON API (`rentcast`), and one local JSON feed (`sample_json_feed`,
deliberately shaped like neither). All four normalize without any schema change needed
for this sprint — but that's a different question from *complete*, and two real gaps
surfaced under honest scrutiny:

**Finding 1 (real gap, not fixed): no `room_type` field exists anywhere.** The v2.0
Step 7 mission's own normalized-output list explicitly asked for "room type," but
`RawListing`/`Apartment` never gained one — RentCast has no such concept (whole-unit
rentals only) so its absence went unnoticed until this sprint. `sample_json_feed`'s
fixture deliberately includes a real `room_category` field
(`"private_room"`/`"entire_unit"`) that `normalize()` receives but cannot map anywhere
— live, checked-in proof of the gap, not a hypothetical. This connects directly to the
already-known, deliberately deferred "room/flatshare filter categories" tension
flagged during the original v2.0 architecture design (`gender`/`room_type`/
`private_bathroom`/`student_only` — see `learning/architecture_notes.md`'s 2026-07-14
entry): adding `room_type` now would reopen that same, still-unresolved product-scope
question, so it's reported here as a finding, not silently fixed.

**Finding 2 (real gap, not fixed): no field carries a platform's own "last updated"
fact.** `Apartment.last_seen_at`/`.first_seen_at` are *this system's own observation
timestamps* — when a search last saw the listing — not the platform's own metadata
about when the listing itself was last modified. RentCast's real schema provides
`lastSeenDate`/`listedDate`; `sample_json_feed`'s fixture provides `last_modified` —
both real, both currently discarded by `normalize()`, because `RawListing` has nowhere
to put them. The Step 7 mission's "last updated timestamp" ask is satisfied today only
in the weaker, system-observation sense, not the platform-native sense a renter would
actually want ("when was this actually posted/changed").

**Finding 3 (gap found and fixed this sprint): fields the model already has weren't
being shown.** `Apartment.currency`, `.property_type`, `.latitude`/`.longitude`,
`.platform_id`, `.platform_listing_id`, and `.description` were all already populated
by connectors (RentCast since Step 7; `sample_json_feed` from day one) but
`services/report_generator.py` never rendered any of them — a presentation gap, not a
model gap, and a safe, small, additive fix rather than a schema change. Fixed this
sprint: the report now shows platform name (via a `platform_registry.get_platform()`
lookup), listing identifier, property type, currency, coordinates, last-observed
timestamp, and description, each rendering `"n/a"` honestly when absent rather than
guessing or omitting silently. Verified by new tests
(`tests/services/test_report_generator.py::EnrichedMetadataSectionTests`).

**What already works well, confirmed across all four connectors**: title, price,
address, bedrooms/bathrooms/sqft, availability/status, images, description, and the
listing URL all have real, working homes in the model, and every connector's honest
gaps (RentCast's missing photos/description; `sample_json_feed`'s null `summary`/empty
`photo_urls` for one listing) normalize to `None`/`[]` without crashing anywhere in the
pipeline — the "missing fields must never crash the connector" guarantee holds for a
fourth, deliberately different data shape, not just the three it was already proven
against.

## Test Suite Impact

15 new tests (428 total: 413 existing untouched + 12 for `sample_json_feed` + 3 for
the report's newly-surfaced fields). The full pre-existing suite passes unmodified.

## Related

- [18_Connector_SDK.md](18_Connector_SDK.md) — the framework being validated
- [20_First_Production_Connector.md](20_First_Production_Connector.md) — RentCast,
  the third connector before this sprint's fourth
- [21_Provider_Abstraction_Layer.md](21_Provider_Abstraction_Layer.md) — the layer
  that already relies on direct `Platform` construction, the same pattern this
  sprint's auto-discovery test uses
- `learning/architecture_notes.md` — the 2026-07-14 "room/flatshare filter
  categories" deferral this sprint's Finding 1 connects back to
