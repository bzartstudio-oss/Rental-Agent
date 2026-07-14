# 05 — Platform Discovery

Status: v1.1 (Multi-Platform Discovery Framework) live in code. v2.0 (Platform
Intelligence section below) designed 2026-07-14, not yet implemented.

## What Changed From v1.0

v1.0's `DiscoveryAgent` was a thin read-only lookup: `discover(request)` returned every
active platform, and registering a platform was a single manual `INSERT`. v1.1 makes
platform *management* a first-class responsibility, not an afterthought — the registry
now tracks rich metadata per platform (country, cities, rental types, login requirements,
whether a connector exists) and the Discovery Agent owns keeping that data accurate over
time, not just reading it at search time.

**Still true from v1.0, unchanged:** no listings are scraped here. Platform Discovery
only ever touches platform-level metadata (a company's name, homepage, what it covers) —
never a single apartment listing. That boundary is deliberate, not a placeholder for
"not built yet."

## Two Roles, One Class

`DiscoveryAgent` (`discovery/discovery_agent.py`) has two distinct responsibilities, kept
as separate methods because they're used at different times by different callers:

1. **Search-facing — `discover(request) -> list[Platform]`.** Called by `core/agent.py`
   for every real search. Returns only platforms with `connector_available = True` —
   there's no point returning a platform `RentalResearchAgent` can't actually query.
2. **Management-facing — `sync_platforms(candidates) -> DiscoveryReport`.** Called
   whenever new or updated platform information is available (see "When Sync Runs"
   below). This is where the five behaviors below live.

## The Five Behaviors of `sync_platforms()`

Given a batch of `PlatformCandidate`s (platform metadata pending registration — see
`discovery_agent.py`), `sync_platforms()`:

1. **Loads existing platforms** — reads the full current registry from `platforms`
   (`discovery/platform_registry.py::list_all_platforms`).
2. **Detects duplicates** — for each candidate, checks whether it matches an existing
   platform by exact `id`, or by normalized homepage domain (strips scheme/`www.`/
   trailing slash, case-insensitive). Deliberately simple — no fuzzy name matching — see
   "Why Not Fuzzy Matching" below.
3. **Updates metadata** — if a duplicate is found, the existing row's fields are
   refreshed from the candidate and `last_verified` is bumped to now, rather than
   inserting a second row for the same platform.
4. **Saves newly discovered platforms** — if no duplicate is found, the candidate is
   inserted as a new `platforms` row.
5. **Marks unsupported platforms** — any candidate (new or updated) with
   `connector_available = False` stays in the registry, clearly flagged as known-but-
   unsupported, rather than being silently dropped or requiring a connector to exist
   before the platform can even be recorded. This is what makes "catalogue real
   platforms before writing scrapers for them" possible at all.

Returns a `DiscoveryReport` (new / updated / duplicate / marked-unsupported platform IDs)
so a caller (the CLI, a future admin tool) can show what changed.

## Why Not Fuzzy Matching

A production platform-discovery system might eventually want fuzzy name matching,
favicon/logo comparison, or WHOIS lookups to catch duplicates that don't share an exact
domain (e.g. a platform's `.com` and a country-specific `.es` mirror). None of that is
built here — exact-id-or-exact-domain is the whole duplicate-detection rule for v1.1.
Building more before there's a real duplicate that the simple rule actually misses would
be solving a problem that hasn't been observed yet, not one that's known to exist.

## When Sync Runs

v1.1 does not build an automated web-crawling discovery mechanism (that's still explicitly
V2 — see below). `sync_platforms()` is called by `ui/cli.py` on every startup against a
static, hand-maintained candidate list (`discovery/known_platforms.py`) — this is what
"discovery" means concretely in v1.1: compiling and maintaining a real catalogue of known
platforms, not automatically finding new ones. `discovery_method` on each candidate
records this honestly (`"manual_research"`, `"manual_seed"`) rather than implying
something more automated happened.

## Platform Candidates: Real Data, No Live Scraping

`discovery/known_platforms.py` seeds two kinds of entries:

- The reference connectors this codebase actually has (`demo_platform`,
  `demo_platform_two`) — `connector_available = True`.
- A curated list of real, well-known rental platforms across several countries
  (Zillow, Apartments.com, Rightmove, Idealista, Fotocasa, ImmoScout24) —
  `connector_available = False`, `discovery_method = "manual_research"`. Their names and
  homepage URLs are public, well-known facts, not scraped data — no live request is made
  to any of these sites to compile this list. Fields that would require actually visiting
  the site to verify (exact `requires_login` behavior, precise `supported_cities`) are
  left conservative (`supported_cities: ["Nationwide"]`) or noted as unverified in
  `notes` rather than guessed at with false confidence.

This is real, useful cataloguing work — and exactly where v1.1 draws the line before
"implement a real connector," per the instruction that started this version.

## Automated Discovery (V2, still not built)

Searching the web for "rental platforms in \<location\>" to find genuinely new,
previously-uncatalogued platforms remains V2 scope. `discovery_method = "web_search"` is
reserved in the schema for when that's built, so `sync_platforms()` doesn't need a schema
change to support it later — it would just be a new source of `PlatformCandidate`s feeding
the same five-behavior pipeline.

## Platform Intelligence (v2.0, designed — not yet implemented)

v1.1's `platforms` table records what a platform *is* (name, country, coverage). v2.0
adds what the system has *learned* about how well it performs: `reliability_score`,
`success_rate`, `avg_response_time_ms`, `avg_apartment_count`, `duplicate_percentage`,
`connector_version` — see [03_Data_Model.md](03_Data_Model.md) for the exact columns.

These are rollups, not independently-set values — `DiscoveryAgent` doesn't compute them
directly. The Knowledge Engine ([16_Knowledge_Engine.md](16_Knowledge_Engine.md)) writes
one `platform_performance_observations` row per platform after every search, then
recomputes the six rollup columns on `platforms` from recent observations. This keeps
`DiscoveryAgent`'s job unchanged (manage identity/metadata) while `platforms` gains a
second kind of information (performance) owned by a different module — the same
separation `apartments.current_price` vs. `apartment_price_history` already established:
one table, two owners, current-state columns are a view over someone else's history.

**Why this doesn't change `sync_platforms()`:** the five behaviors are about *identity and
descriptive metadata* (does this platform exist, what does it cover) — performance is a
different axis entirely, updated on a different cadence (every search) by a different
caller (the Knowledge Engine, from inside `RentalResearchAgent.run()`, not from
`ui/cli.py`'s startup sync). Keeping them as separate write paths avoids
`sync_platforms()` needing to know about search execution at all.

## Related

- [03_Data_Model.md](03_Data_Model.md) — full `platforms` table schema
- [06_Connector_Framework.md](06_Connector_Framework.md) — what `connector_available`/`connector_name` actually enable
- [16_Knowledge_Engine.md](16_Knowledge_Engine.md) — how the Platform Intelligence rollups actually get computed
