# 29 — Automatic Platform Discovery Agent

Version 2.5 Step 13. A provider-independent system that discovers, evaluates,
deduplicates, classifies, verifies, and stores rental-platform *candidates* for a
requested country/region/city/language/rental-category/property-type. It is **not**
about generating connector code, and it is **not** about bypassing authentication,
anti-bot systems, CAPTCHAs, paywalls, robots restrictions, or access controls.
Discovery stays evidence-based, auditable, configurable, and manually triggerable.

## Architecture

`src/discovery/automatic/` is an 8th application of this codebase's established
self-registering plugin shape — the same shape `ConnectorRegistry`/
`AnalysisRegistry`/`ProviderRegistry`/`FilterRegistry`/`GeoProviderRegistry`/
`RankingRuleRegistry`/`FeedbackRegistry` already use:

```
DiscoveryRequest ──▶ AutomaticDiscoveryAgent.run(conn, request)
                          │
                          ├─ 1. platform_registry.list_all_platforms(conn)   (existing, canonical registry)
                          ├─ 2. _should_refresh(conn, request)               (DiscoveryPolicy)
                          ├─ 3. DiscoveryProviderFactory.resolve(...).discover(request)   (per provider)
                          ├─ 4. normalization.normalize_domain()/normalize_name()
                          ├─ 5. normalization.find_duplicate_candidate[_by_name]()
                          ├─ 6. evidence_collection.collect_evidence()
                          ├─ 7. classification.classify_candidate()
                          ├─ 8. verification.verify_domain_accessibility()/verify_homepage_content()
                          ├─ 9. capability.estimate_capabilities()
                          ├─ 10. _calculate_confidence()
                          ├─ 11. service.record_candidate()/record_evidence()/record_verification_result()/
                          │       record_capability_estimate()/record_duplicate_link()
                          └─ 12. statistics.compare_discovery_runs() (via AutomaticDiscoveryAgent.compare_discovery_runs())
                          │
                          ▼
                  PlatformDiscoveryResult (supported / unsupported / needs_review / duplicates)
```

`AutomaticDiscoveryAgent` never owns a `Database` — every method takes `conn`
explicitly, mirroring `FeedbackEngine`'s own shape, so tests drive it against any
fixture connection.

## The Existing Platform Registry is checked first, always

`discovery/discovery_agent.py`/`discovery/platform_registry.py` (the Multi-Platform
Discovery Framework, [05_Platform_Discovery.md](05_Platform_Discovery.md)) remain the
single canonical, active registry, **completely unchanged** by this sprint.
`AutomaticDiscoveryAgent.run()`'s first real step reads
`platform_registry.list_all_platforms(conn)` and builds a normalized-domain lookup —
used to set `matched_platform_id` on any candidate that turns out to already be a
known platform. This lookup is *not* implemented as a `DiscoveryProvider`: providers
self-register eagerly at import time with zero per-call construction parameters (see
"Discovery Providers" below), and a provider needing a live database connection can't
satisfy that constraint. Checking the registry is instead a direct step inside the
agent itself.

## Discovery Lifecycle

For every `DiscoveredURL` a provider returns, the agent:

1. **Normalizes** the URL to a root domain (`normalization.normalize_domain()`,
   reusing `discovery_agent.normalize_homepage()` directly rather than
   reimplementing it) and the platform name (`normalization.normalize_name()`).
2. **Deduplicates** — see "Deduplication" below.
3. **Collects evidence** — see "Platform Evidence" below.
4. **Classifies** — see "Classification" below.
5. **Verifies** — see "Verification" below.
6. **Estimates capabilities** — see "Capability Estimation" below.
7. **Calculates confidence** — see "Confidence Calculation" below.
8. **Stores** the candidate (insert if new, update in place if already known) plus
   every evidence/verification/capability/duplicate-link row generated this pass.

A `DiscoveryRun` row is written at the start of every call (even a refresh-skipped
one, for audit purposes) and finalized with summary counters once the pipeline
finishes.

## Discovery Providers

`DiscoveryProvider` (ABC in `base_provider.py`) has exactly two methods:
`metadata() -> DiscoveryProviderMetadata` and
`discover(request: DiscoveryRequest) -> list[DiscoveredURL]`. Providers register
**instances**, not classes, via `register_discovery_provider()` — no built-in
provider has any per-call construction parameter, so eager self-registration at
import time (in `providers/__init__.py`) is always safe.

Two providers ship this sprint:

- **`curated_seed`** (`providers/curated_seed_provider.py`) — surfaces
  `discovery/known_platforms.py`'s existing public, hand-compiled facts (no live
  request made to any of them), filtered by the request's `country` when given.
  Local fixture entries (`demo_platform`/`demo_platform_two`) are excluded.
- **`manual_url`** (`providers/manual_url_provider.py`) — turns a request's own
  `manual_urls` into candidates, so a manually-supplied URL flows through the exact
  same pipeline as anything a real provider found.

Neither provider makes a network call itself — all network access (a single,
polite homepage fetch) happens later, in the agent's verification step, through the
one injectable `PageFetcher` seam (see "Verification").

### Adding a new provider

1. Subclass `DiscoveryProvider`, set a class-level `provider_id`, implement
   `metadata()` and `discover(request)`.
2. Call `register_discovery_provider(YourProvider())` at module level.
3. Import that module from `providers/__init__.py` (adds the self-registration
   side effect when the package is imported).

No change to `AutomaticDiscoveryAgent`, `DiscoveryProviderRegistry`, or
`DiscoveryProviderFactory` is required — `tests/discovery/automatic/test_registry.py`
proves this directly, by registering an ad-hoc test provider and resolving it purely
through the registry/factory.

## Discovery Request

`DiscoveryRequest` (`models.py`) — every field the mission names, optional where
practical: `country`, `region`, `city`, `postal_area`, `language`,
`rental_categories`, `property_types`, `room_or_shared_housing_intent`,
`long_or_short_term`, `student_housing`, `professional_housing`,
`commercial_rental`, `max_candidates`, `allowed_domains`, `excluded_domains`,
`refresh_policy` (a real `DiscoveryPolicy(max_age_days, force_refresh)`, not a
hidden constant), `minimum_confidence`, `manual_urls`, `discovery_providers` (`None`
= every registered provider). `as_dict()` produces the JSON-safe shape persisted
verbatim as `discovery_runs.request_json`, so a run's exact parameters are always
reproducible later.

## Platform Evidence

`evidence_collection.collect_evidence()` produces the mission's 15 named evidence
fields per candidate. Two of the fifteen (`dates`, `confidence`) are already
first-class fields on `PlatformEvidence` itself (`collected_at`, `confidence`)
rather than a redundant `evidence_type` string; the other thirteen each get their
own row: `discovered_url`, `provider`, `search_phrase_or_seed_source`, `page_title`,
`page_description`, `keywords`, `location_evidence`, `rental_category_evidence`,
`language_evidence`, and (folded from the mission's listing/search-page/API-feed/
login-requirement/robots-observation wording into what's actually collectible
without a second network call) `robots_or_policy_observation` and
`raw_evidence_reference`. Listing-page/search-page presence and login requirement
are recorded as **verification observations** (see below), not duplicated as a
second evidence row for the same finding.

Evidence is strictly append-only — "Never overwrite evidence" (the mission's own
words). No `update_*`/`delete_*` function exists for `platform_evidence` anywhere in
this codebase.

## Classification

`classification.classify_candidate()` is deterministic keyword scoring, never an ML
model. A fixed `_CATEGORY_KEYWORDS` dict maps 11 of the mission's 13
`PlatformClassification` categories to a small, documented keyword tuple (the other
two — `IRRELEVANT` and `UNKNOWN` — are the "nothing matched" fallback outcomes, not
something to positively match toward). A candidate's evidence text (name, source
hint, page title/description) is scored against every category; the highest-scoring
category wins, ties broken by declaration order for full reproducibility.
`classify_candidate()` returns both the winning category and every category's raw
score, so the decision is fully inspectable; `explain_classification()` turns that
into a human-readable justification string.

## Verification

`verification.py` runs two checks per candidate, using a single injectable
`PageFetcher` seam:

- **`domain_accessibility`** — one polite HTTP GET (8-second timeout, an honest
  identifying User-Agent). `"pass"` on a 2xx/3xx response, `"fail"` on anything
  else or a network error — never raises for an ordinary failure.
- **`listing_or_search_page_presence`** / **`login_requirement`** — cheap keyword
  checks against the already-fetched homepage body (never a second network call).
  `login_requirement` deliberately reports `"login_required"`/`"no_login_required"`
  rather than ambiguous `"pass"`/`"fail"` — neither direction reads unambiguously as
  success. Both checks report `"unknown"` (never a fabricated pass/fail) when
  nothing was fetched at all.

`HttpPageFetcher` is the one real `PageFetcher` implementation — no retries, no
JavaScript execution, no login attempt, no CAPTCHA solving, matching "do not bypass
authentication/CAPTCHAs/rate limits/robots restrictions/anti-bot protections" (the
mission's own words). Every test in this codebase instead injects a fake
`PageFetcher` returning a canned `PageFetchResult` — "do not use uncontrolled
scraping in tests" (the mission's own words) — so no test ever makes a real network
call.

Verification failures never erase a candidate: a failed/unknown check is recorded
honestly as a `PlatformVerificationResult` row and the candidate row is updated, not
deleted.

## Capability Estimation

`capability.estimate_capabilities()` produces the mission's 14 named capabilities
(`images`, `prices`, `availability`, `coordinates`, `addresses`, `descriptions`,
`property_types`, `room_sharing`, `pagination`, `search_filters`, `saved_searches`,
`api_or_feed`, `requires_javascript`, `requires_login`, `likely_connector_complexity`)
from small, documented keyword markers against the already-fetched homepage body —
never a second network call. Every `PlatformCapabilityEstimate` is marked
`is_estimate=True` and stays that way until a real connector confirms a capability
directly (not done this sprint). `requires_login` deliberately reuses
`verification.py`'s own `login_requirement` finding rather than re-detecting it, so
the two modules never disagree about the same fact. `likely_connector_complexity` is
a simple, explainable rule of thumb (API/feed advertised + no JS markers + no login
→ `"low"`; JS markers + login required → `"high"`; otherwise `"medium"`), never a
scored/trained model.

## Deduplication

Two tiers, because the mission names two distinct dedup keys that mean genuinely
different things:

1. **Normalized root domain** (`normalization.find_duplicate_candidate()`, folding
   in configured `DOMAIN_ALIASES` and, implicitly, redirect destinations via
   `HttpPageFetcher`'s `final_url`) — a match here means "the same candidate, seen
   again": the existing `platform_candidates` row is updated in place
   (`last_seen_at`/`last_run_id`), never duplicated into a second row.
2. **Platform name normalization**, across a *different* normalized domain
   (`normalization.find_duplicate_candidate_by_name()`) — a match here is a genuine
   second row, linked via a new `platform_duplicate_links` row
   (`matched_by="normalized_name"`) and marked `PlatformStatus.DUPLICATE`. "Store
   duplicate relationships rather than deleting duplicate evidence" (the mission's
   own words): the duplicate candidate's own evidence stays exactly where it is.

## Confidence Calculation

`AutomaticDiscoveryAgent._calculate_confidence()` is the mean of three signals,
each `[0, 1]`, never an ML score:

- `domain_accessibility` result (`1.0` pass / `0.0` fail / `0.5` unknown)
- `listing_or_search_page_presence` result (same scale)
- evidence richness (`min(1.0, evidence_count / 5)`)

Rounded to 3 decimals. A candidate whose confidence falls below
`DiscoveryRequest.minimum_confidence` is routed to `REQUIRES_MANUAL_REVIEW`
regardless of classification.

## Platform Status

The mission's 12 `PlatformStatus` values are assigned by one explicit, ordered
priority list (first match wins) — never an opaque scoring function:

1. `DUPLICATE` — matched another candidate's normalized name under a different domain
2. `INACCESSIBLE` — domain accessibility check failed
3. `REQUIRES_LOGIN` — homepage appears to require login
4. `IRRELEVANT` — classified as irrelevant
5. `CONNECTOR_AVAILABLE` — matched an existing registry platform whose connector is
   genuinely registered/importable (see "Connector SDK Integration")
6. `CONNECTOR_MISSING` — matched an existing registry platform, but no working
   connector
7. `REQUIRES_MANUAL_REVIEW` — confidence below `minimum_confidence`
8. `VERIFIED` — domain reachable, content checked, but classification stayed
   `UNKNOWN`
9. `RELEVANT` — genuinely classified, verified, reasonably confident, not yet
   connected to any registry platform

`UNSUPPORTED` and `DISABLED` are deliberately **not** assigned automatically by the
pipeline — they're human-driven end states, reachable only via
`discovery-cli reject-candidate` (→ `UNSUPPORTED`) or a future manual disable
action. A discovered platform never automatically becomes research-active: only
`CONNECTOR_AVAILABLE` (an already-certified connector) or an explicit human approval
(`discovery-cli approve-candidate`) does that.

## Registry Integration

`discovery/discovery_agent.py`'s `DiscoveryAgent`/`platform_registry.py` remain the
canonical, active registry — untouched by this sprint. This agent only ever
*contributes candidates*; the only path from a `platform_candidates` row to a real
`platforms` row is `discovery-cli approve-candidate`, which builds a
`discovery_agent.PlatformCandidate` from the discovered row and calls the *existing*
`DiscoveryAgent.sync_platforms()` — never a new, parallel insert path. Existing,
manually-maintained platforms are never touched by anything in this sprint.

## Connector SDK Integration

`agent._connector_is_available()` reuses `ConnectorRegistry` exactly as
`ConnectorFactory` already does: `ConnectorRegistry.is_registered(name)` first, then
attempt `ConnectorRegistry.get(name)` (which imports `src.connectors.<name>` on
demand) and treat `ConnectorConfigurationError` as an honest "no connector" — never
a guess, never an invented `True`. `AutomaticDiscoveryAgent.platforms_missing_
connectors()` exposes the queue of verified platforms with no connector yet. No
connector source code is generated by this sprint.

## Approval Workflow

`discovery-cli approve-candidate --candidate-id <id> [--connector-name <name>]`
promotes a candidate into the Platform Registry via `DiscoveryAgent.sync_platforms()`
— `discovery_method="automatic_discovery_approved"`, a `notes` field naming the
source candidate and its classification. `discovery-cli reject-candidate
--candidate-id <id> [--reason <text>]` sets `PlatformStatus.UNSUPPORTED` and records
an auditable `PlatformEvidence` row (`evidence_type="manual_review_decision"`) with
the decision and reason — a rejection is explainable later, not a silent flag flip.

## Compliance Boundaries

This agent never bypasses authentication, access controls, CAPTCHAs, rate limits,
robots restrictions, or anti-bot protections — `HttpPageFetcher` performs exactly
one polite GET per candidate per run, nothing more. It never labels a platform
"safe" or "legally permitted" without evidence; when verification is inconclusive,
the pipeline routes to `REQUIRES_MANUAL_REVIEW` rather than guessing. Robots/access-
policy fetching is explicitly out of scope this sprint — every candidate's evidence
honestly records `{"checked": false, "reason": "robots.txt/access-policy fetch is
out of scope this sprint"}` rather than fabricating a compliance finding.

## Knowledge Engine Integration

Rather than a second, parallel knowledge store, this sprint extends the existing
append-only `discovery_provider_observations` table (one row per provider execution
per run — `candidates_found`, `duration_ms`, `succeeded`, `error`) and adds
`statistics.compute_discovery_statistics()`/`compare_discovery_runs()`, mirroring
`knowledge_service.py`'s own "plain average/count/ratio over already-stored data, no
prediction" discipline. `AutomaticDiscoveryAgent` exposes the mission's own read
methods directly: `latest_discovery()`, `discovery_history()`,
`compare_discovery_runs()`, `new_platforms_since()`, `platforms_needing_review()`,
`platforms_missing_connectors()`, `coverage_summary()`.

## CLI

`src/ui/discovery_cli.py` (kept separate from `ui/cli.py`/`ui/feedback_cli.py`, the
same backward-compatibility reasoning both prior CLIs already established):
`discover` (optionally `--report` to also write an HTML+JSON report),
`list-discovered`, `list-verified`, `list-unsupported`, `list-missing-connectors`,
`compare-runs`, `approve-candidate`, `reject-candidate`, `view-evidence`,
`view-coverage-summary`.

## Interpreting Reports

`discovery/automatic/report.py` writes `<run_id>_discovery.json` and
`<run_id>_discovery.html` (mirrors `services/report_generator.py`'s own "plain
string templating, reproducible from stored data alone" shape — no Jinja2
dependency). Both contain: the original request, providers used, per-candidate
evidence-type counts (an evidence *summary*, not the full evidence dump),
verification results, capability estimates (always clearly estimates), original
discovered URLs, geographic coverage, and any run warnings — split into supported
platforms, unsupported platforms, the manual-review queue, and duplicates.

## Database

Migration `0008_automatic_platform_discovery.sql` — 7 new tables, `platforms`
(migration 0001) and every prior migration completely untouched:
`discovery_runs`, `platform_candidates` (both mutable current-state tables, mirroring
`platforms` itself), and `platform_evidence`/`platform_verification_observations`/
`platform_capability_estimates`/`platform_duplicate_links`/
`discovery_provider_observations` (all strictly append-only — no `update_*`/
`delete_*` function exists for any of them). See
[03_Data_Model.md](03_Data_Model.md) for the full column-by-column reference.

## What's Deliberately Not Built This Sprint

Per the mission's own explicit instructions: connector code generation, continuous
monitoring (periodic re-discovery), and notifications. See
[../notes/Questions.md](../notes/Questions.md) for the open product decisions this
leaves (a real web-search-API provider, `DOMAIN_ALIASES` curation ownership, the
concrete approval-workflow requirements, and monitoring/notification scheduling).
