# 17 — Search Memory

Status: Designed 2026-07-14; **live as of v2.0 Step 3 (2026-07-14)** — see
`src/search_memory/` and `storage/search_memory_repository.py`. Implements
requirement 3.

## What's Already True (v1.1)

Every `SearchRequest` is already persisted (`search_requests`), and its ranked output is
already an immutable snapshot (`search_results`) — see
[03_Data_Model.md](03_Data_Model.md). That's "the complete `SearchRequest`" and part of
"report location" already satisfied. What v2.0 adds is everything about *what happened
during execution*, and the ability to compare one run against another.

## What Gets Added

The eight new `search_requests` columns from [03_Data_Model.md](03_Data_Model.md)
(`execution_time_ms`, `discovered_platform_ids_json`, `searched_platform_ids_json`,
`apartment_count`, `new_apartment_count`, `removed_apartment_count`,
`changed_apartment_count`, `report_path`, `runtime_stats_json`), plus the new
`search_observed_apartments` table (the full observed set, independent of ranking/
filtering — see that doc for why it has to be separate from `search_results`).

Write timing: `search_requests` gets its row at submission (unchanged from v1.1) with the
eight new columns `NULL`; they're filled in via one `UPDATE` after `run()` completes.
`search_observed_apartments` rows are written by the Analysis Engine as it processes each
listing — same timing as `apartment_price_history`/`apartment_change_log` writes.

## Run-Over-Run Comparison

"Future executions must compare against previous runs" requires answering two questions:
**which** previous run, and **what** counts as new/removed/changed.

**Which previous run — matched by `location`, not exact criteria.** Proposed: when a
search completes, find the most recent *other* `search_requests` row with the same
`location` string, regardless of whether its `criteria` matches exactly. Reasoning: a user
tweaking `max_price` between two runs of what is, to them, "the same ongoing search" is
the common case — matching on exact `criteria_json` would mean almost no two runs ever
compare against each other, defeating the point. This is a heuristic, not a strict
identity rule; it's the default, not the only possible comparison (an explicit
"compare against search X" override is a reasonable later addition, not built now).

**What counts as changed — computed from `search_observed_apartments`, not
`search_results`.** Given this run's observed apartment-id set and the matched previous
run's observed set (both from `search_observed_apartments`):

```
new_apartment_count     = |current set − previous set|
removed_apartment_count = |previous set − current set|
changed_apartment_count = apartments in both sets that have at least one
                           apartment_price_history / apartment_availability_history /
                           apartment_change_log row with observed_at strictly after the
                           previous run's created_at
```

Using the full observed set (not the ranked/filtered `search_results`) means "removed"
genuinely means "no longer seen on the platform," not "no longer matches this run's
budget filter" — those are different facts, and conflating them would make the numbers
actively misleading rather than just imprecise.

**"Changed" also covers title/description/images, not just price/status** (implemented
v2.0 Step 3) — an apartment whose only difference between two searches is a retitled
listing or an added/removed photo has genuinely changed; excluding those would be an
arbitrary gap, not a deliberate scope boundary, now that the Apartment History Engine
(v2.0 Step 2) tracks them.

## A Real Bug: Timestamps Aren't Enough to Bound "Changed"

The original plan above ("observed_at strictly after the previous run's `created_at`")
turned out to be wrong once tested against the real pipeline, not just hand-picked test
timestamps. `SearchRequest.created_at` is stamped when the request object is
constructed — *before* discovery, connector fetches, or any Analysis Engine writes
happen. Those writes (a brand-new apartment's initial price/title/image rows) land
strictly *after* that timestamp, by however long processing took. That means a naive
`previous.created_at < observed_at <= current.created_at` window incorrectly counts a
search's **own** initial-observation rows as "changes relative to itself" the very next
time the same location is searched — every apartment showed up as "changed" on a second,
completely unchanged run.

**Fix:** bound each side of the comparison by `search_id`, not raw timestamps. "The
value of field X as of search S" is the latest history entry that either belongs to S
itself (`entry.search_id == S.id`) or was written at/before S started
(`entry.observed_at <= S.created_at`) — matching on identity first sidesteps the
processing-time gap entirely. See `src/search_memory/search_memory_service.py::_value_as_of`
and `learning/architecture_notes.md` for the full writeup; caught by
`tests/core/test_search_memory_integration.py::test_second_run_for_the_same_location_is_a_reproducible_comparison`
running the *real* orchestrator twice against the *real* demo_platform connector, not
just a unit test with artificially-matched timestamps.

## Two Reconstruction Helpers, Not One

Found during the v2.0 Step 4.5 architecture review: this module's `_value_as_of`
(private) and `src/history/history_service.py::previous_version` (public) both
reconstruct "what was this apartment's field worth at some earlier point" from the
same underlying history tables — worth asking why one wasn't reused for the other.
They answer genuinely different questions:

- **`previous_version`** — "what did this apartment look like right before its most
  recent recorded change?" No search identity involved; it just takes the second-newest
  row in each field's own history. A plain, single-apartment read, useful on its own.
- **`_value_as_of`** — "what was this field's value *as of a specific named search*?"
  Needed because `compare_searches(a, b)` lets the caller pick *any* two searches, which
  might not be adjacent in a given apartment's own history at all (other searches may
  have observed it, unchanged, in between `a` and `b`). Answering that requires a
  search identity as an input, which `previous_version` has no use for.

Merging them would mean either bolting an unused `search_id` parameter onto every
`history_service` read (which has nothing to do with comparing two searches), or
weakening `_value_as_of`'s search-identity matching back down to the timestamp-only
approach that caused the real bug documented above. Kept as two small, separately
correct functions instead — see each one's docstring for the cross-reference.

## Where This Runs

Same place as the Knowledge Engine ([16_Knowledge_Engine.md](16_Knowledge_Engine.md)) —
inside `RentalResearchAgent.run()`, after ranking and report generation, since
`report_path` and the comparison counts need the run to have actually finished. Live as
of v2.0 Step 3: `search_memory_service.record_completed_search()` is called there.

## Exposed Methods (v2.0 Step 3, live)

`src/search_memory/search_memory_service.py`, translated from the mission's PascalCase
to this project's snake_case convention: `latest_search`, `search_history`,
`compare_searches`, `search_timeline`, `average_execution_time`,
`average_apartment_count`, `search_statistics`. All deterministic — plain averages and
set/timestamp arithmetic over already-stored data, no prediction or AI, per the explicit
v2.0 Step 3 scope boundary.

## Related

- [03_Data_Model.md](03_Data_Model.md) — `search_requests` extended columns, `search_observed_apartments`
- [09_Report_System.md](09_Report_System.md) — a natural future home for surfacing this comparison in the report itself, not designed here
- [10_Roadmap.md](10_Roadmap.md) — "Version 2.0" Step 3 for the full implementation summary
