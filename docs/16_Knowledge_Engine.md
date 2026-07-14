# 16 — Knowledge Engine

Status: Designed 2026-07-14 — not yet implemented. Implements requirement 1 and the
"self-improving through accumulated knowledge" half of the mission
([00_Project_Vision.md](00_Project_Vision.md)) — the mechanism by which the system gets
better *without* its code changing, per that doc's explicit constraint: "Learning happens
through data, metadata and accumulated observations, NOT by rewriting code."

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
| `ranking_usefulness_score` | This platform's presence in `search_results` vs. its share of candidates | `(platform's fraction of top-N search_results) ÷ (platform's fraction of all candidate apartments this run)`. >1 means the platform is punching above its weight (small volume, disproportionately well-ranked); <1 means high volume but rarely competitive. `N` = whatever the report's top-N is — an implementation-time constant |
| `parsing_success` | Whether `connector.parse()` (via the Connector SDK — [06_Connector_Framework.md](06_Connector_Framework.md)) raised, distinct from a fetch-level failure | Requires the SDK to distinguish fetch errors from parse errors (e.g. separate exception types) — otherwise this collapses to the same signal as `failed` |

`connector reliability` (the mission's phrase) isn't a raw observation — it's the
`platforms.reliability_score` **rollup**, described next.

## Observation Log → Rollup

Same pattern as `apartments.current_price` vs. `apartment_price_history`: the raw log
(`platform_performance_observations`) is append-only and permanent — "store everything
permanently" is satisfied by never deleting or overwriting a row here, full stop. The six
rollup columns on `platforms` ([05_Platform_Discovery.md](05_Platform_Discovery.md)
"Platform Intelligence") are recomputed after every new observation, over a **recent
window** (proposed: last 20 observations for that platform, or all of them if fewer exist)
rather than an all-time average — reliability should reflect *current* behavior; a
platform that had a bad month a year ago shouldn't be permanently marked unreliable. The
window size is a constant, not a schema decision — easy to tune later without a migration.

```
reliability_score        = weighted combination of the other five quality scores
                            (exact weights: implementation-time tuning, not fixed here)
success_rate             = fraction of recent observations where failed = False
avg_response_time_ms     = AVG(response_time_ms) over recent non-null observations
avg_apartment_count      = AVG(results_count) over recent observations
duplicate_percentage     = AVG(duplicate_rate) over recent observations
```

## Learning From Failure

A platform whose connector raised still gets an observation row (`failed = True`,
`results_count = 0`, most quality scores null) — this is deliberate, not an oversight.
`core/agent.py`'s existing `except Exception: continue` (v1.0/v1.1, unchanged) skips a
broken platform's *listings* for the current search, correctly. It must **not** also skip
recording that the failure happened — otherwise `success_rate` only ever sees successes,
which defeats the entire point of tracking reliability. This is the one place v2.0 changes
`RentalResearchAgent.run()`'s existing try/except: the `except` block gains a call to
record the failed observation before `continue`.

## Where This Runs

Inside `RentalResearchAgent.run()` (today) / the future Learning Agent (see
[15_Agent_Architecture.md](15_Agent_Architecture.md)) — right after each platform's
connector call returns (or raises), before moving to the next platform. Not a separate
batch job — the mission says "after every search it must learn," so learning is part of
the search, not a nightly cron.

## Related

- [03_Data_Model.md](03_Data_Model.md) — `platform_performance_observations` schema
- [05_Platform_Discovery.md](05_Platform_Discovery.md) — the `platforms` rollup columns this feeds
- [06_Connector_Framework.md](06_Connector_Framework.md) — the fetch/parse exception distinction `parsing_success` depends on
