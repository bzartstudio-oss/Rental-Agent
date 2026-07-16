-- Migration 0010 — Notification Delivery Engine (v2.5 Step 15): 12 new tables,
-- every prior migration (0001-0009) completely untouched.
--
-- `notification_preferences` is one *current-state* row per preference
-- (mutable, mirrors `saved_searches`), but its actual settings never change in
-- place — every edit appends a new `notification_preference_versions` row and
-- bumps `current_version`, the same "Never overwrite preferences" discipline
-- migration 0009 already established for saved searches.
--
-- `notification_templates` is populated by syncing self-registered Python
-- template classes' metadata into the database (mirrors
-- `filter_engine.sync_filter_definitions()`'s own established pattern) —
-- never user-created rows; the CLI has no "create template" command.
--
-- `notification_deliveries` is the other current-state row (status/
-- attempt_count/next_attempt_at genuinely change as retries proceed) — one row
-- per logical notification, immediate or digest. `notification_delivery_events`
-- is the append-only link table recording exactly which `monitoring_events`
-- rows fed one delivery — this is both "Store the exact event IDs included in
-- each digest" (the mission's own words) and the same traceability for a
-- single-event immediate notification, generalized into one mechanism instead
-- of two.
--
-- Every other table (`notification_batches`, `notification_attempts`,
-- `notification_messages`, `notification_digests`, `rate_limit_observations`,
-- `channel_health_observations`, `notification_acknowledgements`) is strictly
-- append-only: no `update_*`/`delete_*` function is provided for any of them
-- anywhere in this codebase.

CREATE TABLE IF NOT EXISTS notification_preferences (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    preference_id            TEXT NOT NULL UNIQUE,
    profile_id               TEXT NOT NULL,
    saved_search_id           TEXT REFERENCES saved_searches(saved_search_id),
    current_version           INTEGER NOT NULL DEFAULT 1,
    enabled                  INTEGER NOT NULL DEFAULT 1,
    created_at                TEXT NOT NULL,
    updated_at                TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notif_prefs_profile ON notification_preferences(profile_id);
CREATE INDEX IF NOT EXISTS idx_notif_prefs_search ON notification_preferences(saved_search_id);

CREATE TABLE IF NOT EXISTS notification_preference_versions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    preference_id            TEXT NOT NULL REFERENCES notification_preferences(preference_id),
    version                  INTEGER NOT NULL,
    enabled_channels_json      TEXT NOT NULL,
    event_types_json           TEXT NOT NULL,
    minimum_severity           TEXT,
    minimum_significance        REAL NOT NULL DEFAULT 0.0,
    immediate_event_types_json  TEXT NOT NULL,
    digest_event_types_json     TEXT NOT NULL,
    digest_frequency           TEXT,
    quiet_hours_start           TEXT,
    quiet_hours_end             TEXT,
    timezone                   TEXT NOT NULL DEFAULT 'UTC',
    max_per_hour                INTEGER,
    max_per_day                  INTEGER,
    include_images               INTEGER NOT NULL DEFAULT 1,
    include_original_urls         INTEGER NOT NULL DEFAULT 1,
    include_ranking_explanation    INTEGER NOT NULL DEFAULT 1,
    include_geo_summary            INTEGER NOT NULL DEFAULT 1,
    include_preference_explanation  INTEGER NOT NULL DEFAULT 1,
    include_report_links            INTEGER NOT NULL DEFAULT 1,
    language                        TEXT NOT NULL DEFAULT 'en',
    format                          TEXT NOT NULL DEFAULT 'text',
    metadata_json                    TEXT NOT NULL,
    created_at                       TEXT NOT NULL,
    UNIQUE (preference_id, version)
);

CREATE INDEX IF NOT EXISTS idx_notif_pref_versions_current ON notification_preference_versions(preference_id, version);

CREATE TABLE IF NOT EXISTS notification_templates (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name            TEXT NOT NULL,
    version                  INTEGER NOT NULL,
    channel_compatibility_json TEXT NOT NULL,
    description               TEXT NOT NULL,
    registered_at             TEXT NOT NULL,
    UNIQUE (template_name, version)
);

CREATE TABLE IF NOT EXISTS notification_batches (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id                 TEXT NOT NULL UNIQUE,
    batch_type                TEXT NOT NULL,
    started_at                TEXT NOT NULL,
    completed_at               TEXT,
    deliveries_attempted        INTEGER NOT NULL DEFAULT 0,
    deliveries_succeeded         INTEGER NOT NULL DEFAULT 0,
    deliveries_failed             INTEGER NOT NULL DEFAULT 0,
    notes                        TEXT
);

CREATE TABLE IF NOT EXISTS notification_deliveries (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id              TEXT NOT NULL UNIQUE,
    batch_id                  TEXT REFERENCES notification_batches(batch_id),
    profile_id                 TEXT NOT NULL,
    saved_search_id             TEXT REFERENCES saved_searches(saved_search_id),
    saved_search_version         INTEGER,
    preference_id                 TEXT NOT NULL REFERENCES notification_preferences(preference_id),
    preference_version              INTEGER NOT NULL,
    is_digest                        INTEGER NOT NULL DEFAULT 0,
    status                           TEXT NOT NULL,
    channels_json                     TEXT NOT NULL,
    dedup_key                          TEXT NOT NULL,
    idempotency_key                      TEXT NOT NULL UNIQUE,
    created_at                            TEXT NOT NULL,
    next_attempt_at                        TEXT,
    attempt_count                           INTEGER NOT NULL DEFAULT 0,
    acknowledged                             INTEGER NOT NULL DEFAULT 0,
    notes                                     TEXT
);

CREATE INDEX IF NOT EXISTS idx_notif_deliveries_profile_created ON notification_deliveries(profile_id, created_at);
CREATE INDEX IF NOT EXISTS idx_notif_deliveries_search_created ON notification_deliveries(saved_search_id, created_at);
CREATE INDEX IF NOT EXISTS idx_notif_deliveries_status_next ON notification_deliveries(status, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_notif_deliveries_unacknowledged ON notification_deliveries(acknowledged) WHERE acknowledged = 0;
CREATE INDEX IF NOT EXISTS idx_notif_deliveries_dedup_key ON notification_deliveries(dedup_key);

CREATE TABLE IF NOT EXISTS notification_delivery_events (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id              TEXT NOT NULL REFERENCES notification_deliveries(delivery_id),
    event_id                  TEXT NOT NULL REFERENCES monitoring_events(event_id)
);

CREATE INDEX IF NOT EXISTS idx_notif_delivery_events_delivery ON notification_delivery_events(delivery_id);
CREATE INDEX IF NOT EXISTS idx_notif_delivery_events_event ON notification_delivery_events(event_id);

CREATE TABLE IF NOT EXISTS notification_digests (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id              TEXT NOT NULL UNIQUE REFERENCES notification_deliveries(delivery_id),
    frequency                 TEXT NOT NULL,
    period_start                TEXT NOT NULL,
    period_end                   TEXT NOT NULL,
    generated_at                  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notif_digests_period ON notification_digests(period_start, period_end);

CREATE TABLE IF NOT EXISTS notification_attempts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id              TEXT NOT NULL REFERENCES notification_deliveries(delivery_id),
    channel                   TEXT NOT NULL,
    attempt_number              INTEGER NOT NULL,
    status                       TEXT NOT NULL,
    error                          TEXT,
    error_category                  TEXT,
    duration_ms                       INTEGER,
    attempted_at                       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notif_attempts_channel_status ON notification_attempts(channel, status);
CREATE INDEX IF NOT EXISTS idx_notif_attempts_delivery ON notification_attempts(delivery_id);

CREATE TABLE IF NOT EXISTS notification_messages (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id              TEXT NOT NULL REFERENCES notification_deliveries(delivery_id),
    channel                   TEXT NOT NULL,
    subject                     TEXT,
    body_text                     TEXT NOT NULL,
    body_html                       TEXT,
    template_name                     TEXT NOT NULL,
    template_version                    INTEGER NOT NULL,
    language                              TEXT NOT NULL,
    metadata_json                           TEXT NOT NULL,
    generated_at                              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notif_messages_delivery ON notification_messages(delivery_id);

CREATE TABLE IF NOT EXISTS rate_limit_observations (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id               TEXT NOT NULL,
    channel                    TEXT NOT NULL,
    occurred_at                  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_profile_channel_time ON rate_limit_observations(profile_id, channel, occurred_at);

CREATE TABLE IF NOT EXISTS channel_health_observations (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    channel                   TEXT NOT NULL,
    succeeded                   INTEGER NOT NULL,
    error                         TEXT,
    duration_ms                    INTEGER,
    observed_at                      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_channel_health_channel_time ON channel_health_observations(channel, observed_at);

CREATE TABLE IF NOT EXISTS notification_acknowledgements (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id              TEXT NOT NULL REFERENCES notification_deliveries(delivery_id),
    acknowledged_at            TEXT NOT NULL,
    acknowledged_by              TEXT,
    note                           TEXT
);

CREATE INDEX IF NOT EXISTS idx_notif_acknowledgements_delivery ON notification_acknowledgements(delivery_id);
