-- Migration 0008 — Automatic Platform Discovery Agent (v2.5 Step 13): seven new
-- tables, no existing table modified. `platforms` (migration 0001) remains the
-- single canonical, active registry — these tables are a staging area upstream of
-- it: a candidate only ever becomes a `platforms` row through the existing
-- `DiscoveryAgent.sync_platforms()` path, never automatically.
--
-- `platform_candidates` holds one *current-state* row per unique discovered
-- candidate (mutable, like `platforms` itself — classification/status/confidence
-- genuinely change as more evidence arrives) — but every table beneath it
-- (`platform_evidence`, `platform_verification_observations`,
-- `platform_capability_estimates`, `platform_duplicate_links`,
-- `discovery_provider_observations`) is strictly append-only: no `update_*`/
-- `delete_*` function is provided for any of them anywhere in this codebase.
-- Purely additive — 0001-0007 untouched.

CREATE TABLE IF NOT EXISTS discovery_runs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                  TEXT NOT NULL UNIQUE,
    request_json            TEXT NOT NULL,
    started_at              TEXT NOT NULL,
    completed_at            TEXT,
    providers_used_json      TEXT NOT NULL,
    total_candidates        INTEGER NOT NULL DEFAULT 0,
    new_candidate_count       INTEGER NOT NULL DEFAULT 0,
    duplicate_count          INTEGER NOT NULL DEFAULT 0,
    verified_count           INTEGER NOT NULL DEFAULT 0,
    supported_count          INTEGER NOT NULL DEFAULT 0,
    unsupported_count        INTEGER NOT NULL DEFAULT 0,
    notes                   TEXT
);

CREATE INDEX IF NOT EXISTS idx_discovery_runs_started ON discovery_runs(started_at);

CREATE TABLE IF NOT EXISTS platform_candidates (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id            TEXT NOT NULL UNIQUE,
    normalized_domain        TEXT NOT NULL,
    name                    TEXT NOT NULL,
    raw_url                 TEXT NOT NULL,
    country                 TEXT,
    region                  TEXT,
    city                    TEXT,
    status                  TEXT NOT NULL,
    classification           TEXT NOT NULL,
    confidence               REAL,
    matched_platform_id       TEXT REFERENCES platforms(id),
    first_discovered_at       TEXT NOT NULL,
    last_seen_at             TEXT NOT NULL,
    last_run_id              TEXT NOT NULL REFERENCES discovery_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_candidates_domain ON platform_candidates(normalized_domain);
CREATE INDEX IF NOT EXISTS idx_candidates_geo ON platform_candidates(country, region, city);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON platform_candidates(status);

CREATE TABLE IF NOT EXISTS platform_evidence (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id            TEXT NOT NULL REFERENCES platform_candidates(candidate_id),
    run_id                  TEXT NOT NULL REFERENCES discovery_runs(run_id),
    evidence_type            TEXT NOT NULL,
    discovery_provider        TEXT NOT NULL,
    value_json               TEXT NOT NULL,
    confidence               REAL,
    collected_at             TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evidence_candidate ON platform_evidence(candidate_id);
CREATE INDEX IF NOT EXISTS idx_evidence_run ON platform_evidence(run_id);

CREATE TABLE IF NOT EXISTS platform_verification_observations (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id            TEXT NOT NULL REFERENCES platform_candidates(candidate_id),
    run_id                  TEXT NOT NULL REFERENCES discovery_runs(run_id),
    check_type               TEXT NOT NULL,
    result                  TEXT NOT NULL,
    detail_json              TEXT,
    observed_at              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_verification_candidate_time ON platform_verification_observations(candidate_id, observed_at);

CREATE TABLE IF NOT EXISTS platform_capability_estimates (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id            TEXT NOT NULL REFERENCES platform_candidates(candidate_id),
    run_id                  TEXT NOT NULL REFERENCES discovery_runs(run_id),
    capability_key           TEXT NOT NULL,
    estimated_value_json      TEXT NOT NULL,
    is_estimate              INTEGER NOT NULL DEFAULT 1,
    observed_at              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_capabilities_candidate ON platform_capability_estimates(candidate_id);

CREATE TABLE IF NOT EXISTS platform_duplicate_links (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id            TEXT NOT NULL REFERENCES platform_candidates(candidate_id),
    duplicate_of_candidate_id TEXT NOT NULL REFERENCES platform_candidates(candidate_id),
    matched_by               TEXT NOT NULL,
    linked_at                TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_duplicate_links_candidate ON platform_duplicate_links(candidate_id);

CREATE TABLE IF NOT EXISTS discovery_provider_observations (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                  TEXT NOT NULL REFERENCES discovery_runs(run_id),
    provider_id              TEXT NOT NULL,
    candidates_found         INTEGER NOT NULL DEFAULT 0,
    duration_ms              INTEGER,
    succeeded                INTEGER NOT NULL,
    error                   TEXT,
    observed_at              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_provider_observations_provider_time ON discovery_provider_observations(provider_id, observed_at);
