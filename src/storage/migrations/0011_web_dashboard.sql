-- Migration 0011 — Web Dashboard & API (v2.5 Step 16): four new tables, no
-- existing table modified. Purely additive — 0001-0010 untouched.
--
-- `web_jobs` is the local job-runner's persisted record — the mission's own
-- words: "Jobs must survive page refreshes." One current-state row per job
-- (status/progress/current_stage/result_reference genuinely change as a job
-- runs), mirroring `monitoring_runs`'/`platform_candidates`' own "current-
-- state row" shape. Never duplicates `search_requests`/`monitoring_runs` data
-- itself — `request_reference`/`result_reference` are foreign *identifiers*
-- (a search_id, a monitoring_run_id, a discovery run_id) the existing tables
-- already own, not a copy of their content.
--
-- `web_ui_preferences` is a small per-profile key/value store for UI-only
-- settings (e.g. default ranking profile, default result page size) that have
-- no home in any existing engine's own configuration — generic key/value so a
-- new preference never needs a schema migration, the same "no schema churn
-- for a new key" reasoning `knowledge_entries`/`apartment_analysis_metrics`
-- already apply.
--
-- `web_saved_comparisons` stores which apartment ids a user grouped into a
-- comparison view, so returning to `/compare?comparison_id=...` reproduces the
-- same set — never a copy of apartment data itself, just the id list.
--
-- `web_recent_views` is an append-only log of "apartment X viewed at time Y by
-- profile Z", feeding the dashboard's recently-viewed widget — mirrors the
-- append-only shape most history tables in this system already use.

CREATE TABLE IF NOT EXISTS web_jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id               TEXT NOT NULL UNIQUE,
    job_type             TEXT NOT NULL,
    profile_id           TEXT,
    request_reference     TEXT,
    status              TEXT NOT NULL,
    progress             REAL NOT NULL DEFAULT 0.0,
    current_stage         TEXT,
    result_reference      TEXT,
    error_summary         TEXT,
    warnings_json         TEXT NOT NULL DEFAULT '[]',
    cancellation_requested INTEGER NOT NULL DEFAULT 0,
    metadata_json         TEXT NOT NULL DEFAULT '{}',
    created_at            TEXT NOT NULL,
    started_at            TEXT,
    completed_at           TEXT
);

CREATE INDEX IF NOT EXISTS idx_web_jobs_status_created ON web_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_web_jobs_profile ON web_jobs(profile_id);

CREATE TABLE IF NOT EXISTS web_ui_preferences (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id   TEXT NOT NULL,
    key         TEXT NOT NULL,
    value_json   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE(profile_id, key)
);

CREATE TABLE IF NOT EXISTS web_saved_comparisons (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    comparison_id    TEXT NOT NULL UNIQUE,
    profile_id       TEXT,
    name            TEXT,
    apartment_ids_json TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_web_saved_comparisons_profile ON web_saved_comparisons(profile_id);

CREATE TABLE IF NOT EXISTS web_recent_views (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id    TEXT,
    apartment_id   TEXT NOT NULL,
    viewed_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_web_recent_views_profile_viewed ON web_recent_views(profile_id, viewed_at);
