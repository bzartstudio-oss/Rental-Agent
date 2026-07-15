# 16 — Knowledge Engine

Status: Designed 2026-07-14; **live as of v2.0 Step 4 (2026-07-14)** — see
`src/knowledge/` and `storage/platform_intelligence_repository.py`. Implements
requirement 1 and the "self-improving through accumulated knowledge" half of the
mission ([00_Project_Vision.md](00_Project_Vision.md)) — the mechanism by which the
system gets better *without* its code changing, per that doc's explicit constraint:
"Learning happens through data, metadata and accumulated observations, NOT by
rewriting code." No AI, no predictions, no automatic decision-making anywhere in this
module — every public method is a plain count, average, or ratio over already-stored
facts.

## What Gets Learned, and How Each Metric Is Computed

One `platform_performance_observations` row is written per (platform, search) — see
[03_Data_Model.md](03_Data_Model.md) for the table shape. Concrete definitions (the
schema doc deferred these; this doc owns them):

| Metric | Computed from | Definition |
|---|---|---|
| `results_count` | The connector's return value | `len(raw_listings)` |
| `failed` | Whether `connector.search()` raised | `True` if it raised, else `False` — recorded even on failure, not skipped (see "Learning From Failure" below) |
| `response_time_ms` | Wall-clock around the `connector.search()` call | Null if `failed` before any response was received at all |
| `extraction_quality_score` | Each `RawListing`'s field completeness | Average, across this run's listings, of (non-empty fields ÷ expected fields), where expected = `{title, price, url, bedrooms, bathrooms, sqft, address_raw}` |
| `image_quality_score` | `RawListing.image_urls` | Fraction of this run's listings with at least one image URL |
| `availability_quality_score` | **Raw** `RawListing.status`, before normalization | Fraction of listings where the connector actually reported a status, as opposed to it being absent and silently defaulted to `"available"` by `normalizer.py`. Computed from the raw value specifically so that default doesn't mask "platform never told us" as "100% quality" |
| `duplicate_rate` | `RawListing.platform_listing_id` values within one `search()` call | Fraction that share an id with another listing in the *same* result set — a connector/pagination bug signal, not the same thing as re-observing an apartment across searches (that's normal) or cross-platform duplicates (V2, unrelated) |
| `ranking_usefulness_score` | This platform's presence in the ranked results vs. its share of candidates | `(platform's fraction of the top-N ranked apartments) ÷ (platform's fraction of all candidate apartments this run)`. >1 means the platform is punching above its weight (small volume, disproportionately well-ranked); <1 means high volume but rarely competitive. `N = 10` (`src/knowledge/metrics.py::DEFAULT_TOP_N`) — an implementation-time constant, not schema |
| `parsing_success` | Whether `connector.search()` raised | **Simplified from the original plan**: the Connector SDK that would distinguish a fetch failure from a parse failure is v2.0 Step 5, not built yet, so this currently collapses to the same signal as `failed` (`not failed`). Kept as its own column so no schema/model change is needed once the SDK actually splits them — only `knowledge_service.py`'s computation changes |

`connector reliability` (the mission's phrase) isn't a raw observation — it's the
`platforms.reliability_score` **rollup**, described next.

**Two deviations from the original plan, both about `response_time_ms`/`availability_quality_score`:**
- `response_time_ms` is measured for *every* attempt, including failures (wall-clock
  around the whole `connector.search()` call, success or exception) — not left `NULL`
  on failure as originally sketched. There's no way to tell, without the not-yet-built
  Connector SDK, whether a failure happened before or after "a response was received,"
  so recording the elapsed time regardless is more honest than guessing which failures
  get a number and which don't.
- `availability_quality_score` required a small, deliberate change to
  `connectors/base.py::RawListing.status`: it used to default to the string
  `"available"`, which made "the connector explicitly said available" and "the
  connector didn't set status and got the default" indistinguishable — exactly what
  this metric needs to tell apart. Changed the default to `None`; the actual
  "default to available" behavior moved to `normalizer.py` (which already did
  `raw.status or "available"` and needed no change). Both reference connectors set
  `status` explicitly, so this was a zero-behavior-change fix for existing code.

## Observation Log → Rollup

Same pattern as `apartments.current_price` vs. `apartment_price_history`: the raw log
(`platform_performance_observations`) is append-only and permanent — "store everything
permanently" is satisfied by never deleting or overwriting a row here, full stop. Five
of the six rollup columns on `platforms` ([05_Platform_Discovery.md](05_Platform_Discovery.md)
"Platform Intelligence") are recomputed after every new observation, over a **recent
window of the last 20 observations** for that platform (`src/knowledge/knowledge_service.py::_RECENT_WINDOW`),
or all of them if fewer exist — reliability reflects *current* behavior; a platform
that had a bad month a year ago isn't permanently marked unreliable. `connector_version`
is the sixth column and stays untouched/dormant — nothing yet detects it.

```
reliability_score        = equal-weighted mean of {extraction_quality_score,
                            image_quality_score, availability_quality_score,
                            (1 - duplicate_rate)} over the recent window, excluding
                            None components — ranking_usefulness_score is deliberately
                            NOT included (differently scaled — see below)
success_rate             = fraction of recent observations where failed = False
avg_response_time_ms     = AVG(response_time_ms) over recent observations
avg_apartment_count      = AVG(results_count) over recent observations
duplicate_percentage     = AVG(duplicate_rate) over recent observations
```

`ranking_usefulness_score` is excluded from `reliability_score`'s blend because it's a
ratio that can exceed 1.0 (a platform "punching above its weight"), unlike the other
four components which are naturally bounded to `[0, 1]` — folding it in would let a
single lucky ranking result distort the overall reliability figure. It's still tracked
per-observation and surfaced separately via `PlatformKnowledge.avg_ranking_score`
(`src/knowledge/knowledge_service.py`).

## Learning From Failure

A platform whose connector raised still gets an observation row (`failed = True`,
`results_count = 0`, most quality scores null) — this is deliberate, not an oversight.
`core/agent.py`'s `except Exception: continue` (v1.0/v1.1) skips a broken platform's
*listings* for the current search, correctly, but no longer skips recording that the
failure happened — the `except` block now also captures the raw metrics
(`response_time_ms`, `failed=True`, `raw_listings=None`) needed to write that
observation later in `run()`, alongside every successful platform's.

## Where This Runs

Inside `RentalResearchAgent.run()` — but in two phases, not one, because
`ranking_usefulness_score` needs the ranked results, which don't exist yet right after
a connector call returns:

1. **Right after each platform's `connector.search()` call** (returns or raises):
   `results_count`, `failed`, `response_time_ms`, and — for successes — the raw
   `RawListing`s themselves are captured into an in-memory list. Nothing is written to
   the database yet.
2. **After ranking, and after Search Memory's `record_completed_search()`** (the
   mission's explicit Apartment History -> Search Memory -> Knowledge Engine
   ordering): for each captured platform, `ranking_usefulness_score` is computed from
   the now-available ranked list, and `knowledge_service.record_platform_observation()`
   writes the complete observation row (and recomputes that platform's rollups) in one
   `INSERT` — never a separate `INSERT` followed by an `UPDATE` of the same row.

Not a separate batch job — the mission says "after every search it must learn," so
learning is part of the search itself, not a nightly cron.

## Verified Against the Real Dev Database

Ran the real CLI against `data/rental_intelligence.db`: `demo_platform` and
`demo_platform_two` each got a real `platform_performance_observations` row and a
correctly-computed `reliability_score`/`success_rate` on the `platforms` table, while
platforms never actually searched (`zillow`, `idealista`, etc., still
`connector_available = False`) correctly show `reliability_score = NULL` rather than a
fabricated `0` — "no evidence yet," not "confirmed unreliable."

## Related

- [03_Data_Model.md](03_Data_Model.md) — `platform_performance_observations` schema
- [05_Platform_Discovery.md](05_Platform_Discovery.md) — the `platforms` rollup columns this feeds
- [06_Connector_Framework.md](06_Connector_Framework.md) — the fetch/parse exception distinction `parsing_success` would need the (not yet built) Connector SDK for
- [10_Roadmap.md](10_Roadmap.md) — "Version 2.0" Step 4 for the full implementation summary, including the Cities/Connectors/Searches tracking the v2.0 Step 4 mission also asked for (computed on demand from already-stored data, no new schema)
