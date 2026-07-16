-- Migration 0009 — Continuous Monitoring & Saved Search Engine (v2.5 Step 14):
-- nine new tables, no existing table modified. Purely additive — 0001-0008
-- untouched.
--
-- `saved_searches` holds one *current-state* row per saved search (mutable,
-- like `platforms`/`platform_candidates` — name/description/enabled/
-- current_version genuinely change), but its actual definition never does:
-- every edit appends a new `saved_search_versions` row instead, and
-- `current_version` is bumped to point at it — "Never overwrite a saved
-- search definition" (the mission's own words).
--
-- `monitoring_schedules` is likewise one current-state row per saved search —
-- it doubles as both "when is this due next" bookkeeping and the run-claim
-- lock (`claimed_by`/`claim_expires_at`), so a worker claims a due run with a
-- single conditional `UPDATE ... WHERE claimed_by IS NULL OR claim_expires_at < ?`
-- (SQLite-compatible; no `SELECT ... FOR UPDATE` needed for a single-writer
-- SQLite database).
--
-- Every table beneath those two is strictly append-only: `monitoring_runs`,
-- `monitoring_events`, `event_acknowledgements`, `monitoring_statistics`,
-- `report_artifacts` never get an `update_*`/`delete_*` function anywhere in
-- this codebase, except `monitoring_events.acknowledged` — a single current-
-- state flag on an otherwise-append-only row, mirroring
-- `platform_candidates.status`'s "current-state field on an otherwise mostly-
-- immutable row" shape; `event_acknowledgements` is the actual append-only
-- audit trail of *who*/*when* acknowledged, kept separate from the flag so
-- both a fast "is this acked" lookup and a full history exist.

CREATE TABLE IF NOT EXISTS saved_searches (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    saved_search_id          TEXT NOT NULL UNIQUE,
    profile_id               TEXT,
    name                    TEXT NOT NULL,
    description              TEXT,
    current_version          INTEGER NOT NULL DEFAULT 1,
    enabled                 INTEGER NOT NULL DEFAULT 1,
    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_saved_searches_enabled ON saved_searches(enabled);
CREATE INDEX IF NOT EXISTS idx_saved_searches_profile ON saved_searches(profile_id);

CREATE TABLE IF NOT EXISTS saved_search_versions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    saved_search_id          TEXT NOT NULL REFERENCES saved_searches(saved_search_id),
    version                 INTEGER NOT NULL,
    request_json             TEXT NOT NULL,
    active_filters_json       TEXT NOT NULL,
    ranking_profile_json      TEXT,
    feedback_mode            TEXT,
    selected_platforms_json   TEXT NOT NULL,
    selected_connectors_json  TEXT NOT NULL,
    geographic_destinations_json TEXT NOT NULL,
    monitoring_policy_json   TEXT NOT NULL,
    report_options_json       TEXT NOT NULL,
    retention_policy_json     TEXT NOT NULL,
    tags_json                TEXT NOT NULL,
    metadata_json            TEXT NOT NULL,
    created_at               TEXT NOT NULL,
    UNIQUE (saved_search_id, version)
);

CREATE INDEX IF NOT EXISTS idx_search_versions_search ON saved_search_versions(saved_search_id, version);

CREATE TABLE IF NOT EXISTS monitoring_schedules (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    saved_search_id          TEXT NOT NULL UNIQUE REFERENCES saved_searches(saved_search_id),
    next_run_at              TEXT,
    last_run_at              TEXT,
    last_run_status          TEXT,
    claimed_by               TEXT,
    claimed_at               TEXT,
    claim_expires_at         TEXT
);

CREATE INDEX IF NOT EXISTS idx_schedules_next_run ON monitoring_schedules(next_run_at);
CREATE INDEX IF NOT EXISTS idx_schedules_claim_expiry ON monitoring_schedules(claim_expires_at);

CREATE TABLE IF NOT EXISTS monitoring_runs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    monitoring_run_id        TEXT NOT NULL UNIQUE,
    saved_search_id          TEXT NOT NULL REFERENCES saved_searches(saved_search_id),
    saved_search_version      INTEGER NOT NULL,
    search_id                TEXT REFERENCES search_requests(id),
    status                  TEXT NOT NULL,
    started_at               TEXT NOT NULL,
    completed_at             TEXT,
    platforms_attempted_json  TEXT NOT NULL,
    platforms_succeeded_json  TEXT NOT NULL,
    platforms_failed_json    TEXT NOT NULL,
    event_count              INTEGER NOT NULL DEFAULT 0,
    notes                   TEXT
);

CREATE INDEX IF NOT EXISTS idx_monitoring_runs_search_time ON monitoring_runs(saved_search_id, started_at);
CREATE INDEX IF NOT EXISTS idx_monitoring_runs_status ON monitoring_runs(status);

CREATE TABLE IF NOT EXISTS monitoring_events (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id                 TEXT NOT NULL UNIQUE,
    monitoring_run_id        TEXT NOT NULL REFERENCES monitoring_runs(monitoring_run_id),
    saved_search_id          TEXT NOT NULL REFERENCES saved_searches(saved_search_id),
    saved_search_version      INTEGER NOT NULL,
    search_id                TEXT REFERENCES search_requests(id),
    apartment_id             TEXT REFERENCES apartments(id),
    platform_id              TEXT REFERENCES platforms(id),
    connector_id             TEXT,
    event_type               TEXT NOT NULL,
    severity                TEXT NOT NULL,
    significance             REAL NOT NULL,
    old_value_json           TEXT,
    new_value_json           TEXT,
    explanation              TEXT NOT NULL,
    evidence_json            TEXT NOT NULL,
    detected_at              TEXT NOT NULL,
    dedup_key                TEXT NOT NULL,
    acknowledged             INTEGER NOT NULL DEFAULT 0,
    notification_eligible    INTEGER NOT NULL DEFAULT 1,
    metadata_json            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_type_time ON monitoring_events(event_type, detected_at);
CREATE INDEX IF NOT EXISTS idx_events_apartment_type ON monitoring_events(apartment_id, event_type);
CREATE INDEX IF NOT EXISTS idx_events_platform_type ON monitoring_events(platform_id, event_type);
CREATE INDEX IF NOT EXISTS idx_events_unacknowledged ON monitoring_events(acknowledged) WHERE acknowledged = 0;
CREATE INDEX IF NOT EXISTS idx_events_dedup_key ON monitoring_events(dedup_key);
CREATE INDEX IF NOT EXISTS idx_events_search ON monitoring_events(saved_search_id, detected_at);

CREATE TABLE IF NOT EXISTS event_acknowledgements (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id                 TEXT NOT NULL REFERENCES monitoring_events(event_id),
    acknowledged_at          TEXT NOT NULL,
    acknowledged_by          TEXT,
    note                    TEXT
);

CREATE INDEX IF NOT EXISTS idx_acknowledgements_event ON event_acknowledgements(event_id);

CREATE TABLE IF NOT EXISTS monitoring_statistics (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    monitoring_run_id        TEXT NOT NULL REFERENCES monitoring_runs(monitoring_run_id),
    computed_at              TEXT NOT NULL,
    statistics_json          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_monitoring_statistics_run ON monitoring_statistics(monitoring_run_id);

CREATE TABLE IF NOT EXISTS report_artifacts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    monitoring_run_id        TEXT NOT NULL REFERENCES monitoring_runs(monitoring_run_id),
    report_type              TEXT NOT NULL,
    path                    TEXT NOT NULL,
    generated_at             TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_report_artifacts_run ON report_artifacts(monitoring_run_id);
