-- Migration 0005 — Dynamic Filter Engine (v2.5 Step 9): a genuinely new capability
-- ("Filter History" — search id, filter set, execution time, results count, filter
-- statistics) with no existing table to reuse. `search_requests.criteria_json`
-- already stores the filter set used *for the whole search*, but nothing records
-- per-filter execution statistics (individual pass rates, composed match count) —
-- that's what `statistics_json` holds here. Purely additive — 0001-0004 untouched.

CREATE TABLE IF NOT EXISTS filter_execution_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id           TEXT NOT NULL REFERENCES search_requests(id),
    filter_set_json     TEXT NOT NULL,
    execution_time_ms   INTEGER,
    total_apartments    INTEGER NOT NULL,
    matched_count       INTEGER NOT NULL,
    statistics_json     TEXT NOT NULL,
    recorded_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_filter_history_search ON filter_execution_history(search_id);
