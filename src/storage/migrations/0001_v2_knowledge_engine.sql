-- Migration 0001 — Version 2.0: Autonomous Rental Intelligence Platform schema.
-- Every change here is documented in docs/03_Data_Model.md — this migration contains no
-- schema beyond what's already designed there. Applied automatically by
-- storage/database.py; see that module and docs/10_Roadmap.md "Migration Plan" for how.
--
-- Entirely additive: 6 new tables, all-nullable/defaulted new columns on 4 existing
-- tables. No existing column is dropped, renamed, or made non-nullable — a database with
-- real v1.1 data migrates in place, no reset required (unlike the v1.1 `platforms`
-- rework, which did require one).

-- ---------------------------------------------------------------------------
-- New columns on existing tables
-- ---------------------------------------------------------------------------

-- platforms: Platform Intelligence rollups (docs/05_Platform_Discovery.md), computed by
-- the future Knowledge Engine — all NULL until that logic exists (not built this sprint).
ALTER TABLE platforms ADD COLUMN connector_version TEXT;
ALTER TABLE platforms ADD COLUMN reliability_score REAL;
ALTER TABLE platforms ADD COLUMN success_rate REAL;
ALTER TABLE platforms ADD COLUMN avg_response_time_ms REAL;
ALTER TABLE platforms ADD COLUMN avg_apartment_count REAL;
ALTER TABLE platforms ADD COLUMN duplicate_percentage REAL;

-- apartments: required before its changes can be tracked in apartment_change_log.
ALTER TABLE apartments ADD COLUMN description TEXT;

-- apartment_images: optional cached thumbnail; whether this image is still on the
-- listing as of the most recent observation (never deleted when removed — flipped to 0).
ALTER TABLE apartment_images ADD COLUMN thumbnail_path TEXT;
ALTER TABLE apartment_images ADD COLUMN is_current INTEGER NOT NULL DEFAULT 1;

-- search_requests: turns the row from "what was asked" into Search Memory — "what was
-- asked and what happened." All NULL until RentalResearchAgent.run() is updated to fill
-- them in (not built this sprint).
ALTER TABLE search_requests ADD COLUMN execution_time_ms INTEGER;
ALTER TABLE search_requests ADD COLUMN discovered_platform_ids_json TEXT;
ALTER TABLE search_requests ADD COLUMN searched_platform_ids_json TEXT;
ALTER TABLE search_requests ADD COLUMN apartment_count INTEGER;
ALTER TABLE search_requests ADD COLUMN new_apartment_count INTEGER;
ALTER TABLE search_requests ADD COLUMN removed_apartment_count INTEGER;
ALTER TABLE search_requests ADD COLUMN changed_apartment_count INTEGER;
ALTER TABLE search_requests ADD COLUMN report_path TEXT;
ALTER TABLE search_requests ADD COLUMN runtime_stats_json TEXT;

-- ---------------------------------------------------------------------------
-- New tables
-- ---------------------------------------------------------------------------

-- Generic append-only change log — catches title/description/future fields without a
-- schema migration per field. Not used for price/status, which keep their own tables.
CREATE TABLE IF NOT EXISTS apartment_change_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    apartment_id  TEXT NOT NULL REFERENCES apartments(id),
    field_name    TEXT NOT NULL,
    old_value     TEXT,
    new_value     TEXT NOT NULL,
    search_id     TEXT REFERENCES search_requests(id),
    observed_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_change_log_apartment ON apartment_change_log(apartment_id);

-- Append-only log of images appearing/disappearing between searches.
CREATE TABLE IF NOT EXISTS apartment_image_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    apartment_id  TEXT NOT NULL REFERENCES apartments(id),
    event         TEXT NOT NULL,
    source_url    TEXT NOT NULL,
    search_id     TEXT NOT NULL REFERENCES search_requests(id),
    observed_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_image_events_apartment ON apartment_image_events(apartment_id);

-- Every apartment observed during a search — the FULL set, not just the ranked/filtered
-- subset in search_results. See docs/17_Search_Memory.md for why the distinction matters.
CREATE TABLE IF NOT EXISTS search_observed_apartments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id     TEXT NOT NULL REFERENCES search_requests(id),
    apartment_id  TEXT NOT NULL REFERENCES apartments(id),
    observed_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observed_search ON search_observed_apartments(search_id);
CREATE INDEX IF NOT EXISTS idx_observed_apartment ON search_observed_apartments(apartment_id);

-- The Knowledge Engine's raw, append-only memory — one row per (platform, search). See
-- docs/16_Knowledge_Engine.md for exact metric definitions; platforms' six rollup columns
-- above are aggregates over this table.
CREATE TABLE IF NOT EXISTS platform_performance_observations (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id                 TEXT NOT NULL REFERENCES platforms(id),
    search_id                   TEXT NOT NULL REFERENCES search_requests(id),
    results_count               INTEGER NOT NULL,
    failed                      INTEGER NOT NULL,
    response_time_ms            INTEGER,
    extraction_quality_score    REAL,
    image_quality_score         REAL,
    availability_quality_score  REAL,
    duplicate_rate              REAL,
    ranking_usefulness_score    REAL,
    parsing_success             INTEGER NOT NULL,
    observed_at                 TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_performance_platform ON platform_performance_observations(platform_id);
CREATE INDEX IF NOT EXISTS idx_performance_search ON platform_performance_observations(search_id);

-- Metadata registry for the Dynamic Filter Engine (docs/04_Search_Request.md) — what
-- filters exist, kept queryable as data. Matching/scoring logic stays in Python.
CREATE TABLE IF NOT EXISTS filter_definitions (
    key                           TEXT PRIMARY KEY,
    display_name                  TEXT NOT NULL,
    category                      TEXT NOT NULL,
    value_type                    TEXT NOT NULL,
    applicable_rental_types_json  TEXT NOT NULL,
    description                   TEXT,
    created_at                    TEXT NOT NULL
);

-- The Deep Analysis Engine's output store (docs/07_Analysis_Engine.md) — generic
-- key/value so a new metric type doesn't need a schema migration. Append-only: a metric
-- that changes gets a new row, never an overwrite.
CREATE TABLE IF NOT EXISTS apartment_analysis_metrics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    apartment_id  TEXT NOT NULL REFERENCES apartments(id),
    metric_name   TEXT NOT NULL,
    metric_value  REAL NOT NULL,
    metric_unit   TEXT,
    source_module TEXT NOT NULL,
    search_id     TEXT REFERENCES search_requests(id),
    computed_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analysis_metrics_apartment ON apartment_analysis_metrics(apartment_id);
