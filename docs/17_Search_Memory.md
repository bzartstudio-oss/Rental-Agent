# 17 — Search Memory

Status: Designed 2026-07-14 — not yet implemented. Implements requirement 3.

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

## Where This Runs

Same place as the Knowledge Engine ([16_Knowledge_Engine.md](16_Knowledge_Engine.md)) —
inside `RentalResearchAgent.run()` (today) / the future Learning Agent
([15_Agent_Architecture.md](15_Agent_Architecture.md)), after ranking and report
generation, since `report_path` and the comparison counts need the run to have actually
finished.

## Related

- [03_Data_Model.md](03_Data_Model.md) — `search_requests` extended columns, `search_observed_apartments`
- [09_Report_System.md](09_Report_System.md) — a natural future home for surfacing this comparison in the report itself, not designed here
