-- Migration 0007 — User Feedback and Preference Learning Engine (v2.5 Step 12):
-- four genuinely new tables, no existing table to reuse. `feedback_events` is the
-- append-only raw log ("Never overwrite feedback events. Feedback storage must be
-- append-only" — the mission's own words); `preference_observations` is one
-- computed, persisted verdict per event per preference (auditability: a stored
-- observation is reproducible without re-deriving it from scratch);
-- `preference_adjustments` is the append-only log of every time a preference's
-- computed value actually changed (undo = a new row reversing a prior one, never a
-- delete/update); `preference_snapshots` is a versioned full-profile serialization
-- for compare_preference_profiles()/history. Purely additive — 0001-0006 untouched.

CREATE TABLE IF NOT EXISTS feedback_events (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id                TEXT NOT NULL UNIQUE,
    profile_id              TEXT NOT NULL,
    search_id               TEXT REFERENCES search_requests(id),
    apartment_id            TEXT,
    event_type              TEXT NOT NULL,
    event_value_json         TEXT NOT NULL,
    occurred_at             TEXT NOT NULL,
    source                  TEXT NOT NULL,
    session_id              TEXT,
    metadata_json            TEXT NOT NULL,
    ranking_profile_json      TEXT,
    search_filters_json       TEXT
);

CREATE INDEX IF NOT EXISTS idx_feedback_events_profile_time ON feedback_events(profile_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_feedback_events_apartment_type ON feedback_events(apartment_id, event_type);
CREATE INDEX IF NOT EXISTS idx_feedback_events_search_time ON feedback_events(search_id, occurred_at);

CREATE TABLE IF NOT EXISTS preference_observations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id          TEXT NOT NULL,
    preference_key       TEXT NOT NULL,
    event_id             TEXT NOT NULL REFERENCES feedback_events(event_id),
    direction            TEXT NOT NULL,
    magnitude            REAL NOT NULL,
    observed_value_json   TEXT,
    source_type          TEXT NOT NULL,
    computed_at          TEXT NOT NULL,
    explanation          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pref_observations_profile_key ON preference_observations(profile_id, preference_key);
CREATE INDEX IF NOT EXISTS idx_pref_observations_event ON preference_observations(event_id);

CREATE TABLE IF NOT EXISTS preference_adjustments (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id                  TEXT NOT NULL,
    preference_key               TEXT NOT NULL,
    previous_value_json           TEXT,
    new_value_json                TEXT,
    previous_confidence          REAL,
    new_confidence                REAL,
    reason                      TEXT NOT NULL,
    triggered_by_event_ids_json    TEXT NOT NULL,
    adjustment_type              TEXT NOT NULL,
    reverses_adjustment_id        INTEGER REFERENCES preference_adjustments(id),
    applied_at                  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pref_adjustments_profile_key ON preference_adjustments(profile_id, preference_key);
CREATE INDEX IF NOT EXISTS idx_pref_adjustments_applied_at ON preference_adjustments(applied_at);

CREATE TABLE IF NOT EXISTS preference_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id       TEXT NOT NULL,
    snapshot_json     TEXT NOT NULL,
    reason           TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pref_snapshots_profile_created ON preference_snapshots(profile_id, created_at);
