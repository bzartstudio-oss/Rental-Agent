# 08 — Ranking System

Status: V1.0 design confirmed (2026-07-14) — weighted-sum scoring, same registry pattern as `search/criteria.py`.

## Goal

Take normalized `Apartment` records from the [07_Analysis_Engine.md](07_Analysis_Engine.md) and produce ranked, scored results against a `SearchRequest` ([04_Search_Request.md](04_Search_Request.md)), persisted as `search_results` rows ([03_Data_Model.md](03_Data_Model.md)).

## Design: Scoring Mirrors the Filter Registry

Principle 5 ("all filters are configurable and extensible") applies to ranking too, not just hard filtering — so `ranking/scoring.py` uses the same registered-criteria approach as `search/criteria.py` ([04_Search_Request.md](04_Search_Request.md)): each registered filter can optionally contribute a **scoring function** in addition to its pass/fail matching behavior. A new filter type gets ranking support for free by implementing one extra method, rather than the Ranking Engine needing a hardcoded `if criteria_key == "..."` branch per filter.

```
RankingEngine.rank(apartments: list[Apartment], request: SearchRequest) -> list[RankedApartment]
  for each apartment:
    for each criterion in request.criteria:
      if criterion has a scoring function:
        contribution = scoring_fn(apartment, criterion.value)
        score += contribution * criterion.weight
        score_breakdown[criterion.key] = contribution
  sort by score descending
```

## Scoring Approach: Weighted Sum (V1.0 decision)

Chosen over a model-based scoring approach for V1.0: weighted sum is transparent — every score is explainable as a sum of named contributions, which matters because `score_breakdown_json` (see [03_Data_Model.md](03_Data_Model.md)) is persisted and the Report Generator ([09_Report_System.md](09_Report_System.md)) can show *why* an apartment ranked where it did. A black-box model would defeat that. Revisit only if weighted sum proves genuinely insufficient once real data exists to evaluate against.

## Ranking Criteria (V1.0 starting set)

Matches the filter registry in [04_Search_Request.md](04_Search_Request.md) — budget fit, location/distance fit, listing freshness (`first_seen_at`/`last_seen_at`), any explicit criteria from the request.

## Configurability

Weights are per-`SearchRequest` (part of `criteria`, e.g. `{"max_price": {"value": 2000, "weight": 2.0}}`), not global constants — this is what "configurable" means here, consistent with Principle 5.

## Open Questions

- Default weights when a `SearchRequest` doesn't specify one for a given criterion — flat default (e.g. `1.0`) is the obvious starting choice, confirm once there's a real search to tune against.
