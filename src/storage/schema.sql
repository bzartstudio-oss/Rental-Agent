-- Rental Intelligence Platform — SQLite schema (V1.0)
-- Design rationale for every table: docs/03_Data_Model.md
-- This file is applied by storage/database.py on first connection (CREATE TABLE IF NOT EXISTS,
-- so it's always safe to run against an existing database).

PRAGMA foreign_keys = ON;

-- The Platform Registry (docs/05_Platform_Discovery.md)
CREATE TABLE IF NOT EXISTS platforms (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    base_url         TEXT NOT NULL,
    connector_module TEXT NOT NULL,
    is_active        INTEGER NOT NULL DEFAULT 1,
    created_at       TEXT NOT NULL,
    notes            TEXT
);

-- Current-state apartment records. History lives in the tables below, never here.
CREATE TABLE IF NOT EXISTS apartments (
    id                   TEXT PRIMARY KEY,
    platform_id          TEXT NOT NULL REFERENCES platforms(id),
    platform_listing_id  TEXT NOT NULL,
    title                TEXT NOT NULL,
    bedrooms             REAL,
    bathrooms            REAL,
    sqft                 REAL,
    address_raw          TEXT,
    address_normalized   TEXT,  -- JSON
    latitude             REAL,
    longitude            REAL,
    url                  TEXT NOT NULL,
    current_price        REAL NOT NULL,
    current_status       TEXT NOT NULL,
    first_seen_at        TEXT NOT NULL,
    last_seen_at         TEXT NOT NULL,
    merged_into_id       TEXT REFERENCES apartments(id),  -- unused in V1, reserved for V2 dedup
    UNIQUE (platform_id, platform_listing_id)
);

CREATE INDEX IF NOT EXISTS idx_apartments_platform ON apartments(platform_id);

-- One row per submitted SearchRequest (docs/04_Search_Request.md).
-- criteria_json is the full request, serialized exactly as submitted — this is what
-- makes a search reproducible (docs/00_Project_Vision.md Principle 4).
CREATE TABLE IF NOT EXISTS search_requests (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    label         TEXT,
    criteria_json TEXT NOT NULL
);

-- Append-only. A new row is written only when the price actually changes
-- (see docs/07_Analysis_Engine.md "change detection") — this table is never UPDATEd or DELETEd from.
CREATE TABLE IF NOT EXISTS apartment_price_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    apartment_id  TEXT NOT NULL REFERENCES apartments(id),
    price         REAL NOT NULL,
    observed_at   TEXT NOT NULL,
    search_id     TEXT REFERENCES search_requests(id)
);

CREATE INDEX IF NOT EXISTS idx_price_history_apartment ON apartment_price_history(apartment_id);

-- Append-only, same shape as price history, for availability/status changes.
CREATE TABLE IF NOT EXISTS apartment_availability_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    apartment_id  TEXT NOT NULL REFERENCES apartments(id),
    status        TEXT NOT NULL,
    observed_at   TEXT NOT NULL,
    search_id     TEXT REFERENCES search_requests(id)
);

CREATE INDEX IF NOT EXISTS idx_availability_history_apartment ON apartment_availability_history(apartment_id);

CREATE TABLE IF NOT EXISTS apartment_images (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    apartment_id   TEXT NOT NULL REFERENCES apartments(id),
    source_url     TEXT NOT NULL,
    local_path     TEXT NOT NULL,
    position       INTEGER NOT NULL DEFAULT 0,
    downloaded_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_images_apartment ON apartment_images(apartment_id);

-- Immutable snapshot of one search's ranked output. price_at_search/status_at_search are
-- deliberately denormalized (copied, not joined) so an old report never silently changes
-- as apartments.current_price/current_status are updated by later searches.
-- See docs/03_Data_Model.md "The Versioning Principle, Concretely".
CREATE TABLE IF NOT EXISTS search_results (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id             TEXT NOT NULL REFERENCES search_requests(id),
    apartment_id          TEXT NOT NULL REFERENCES apartments(id),
    rank                  INTEGER NOT NULL,
    score                 REAL NOT NULL,
    score_breakdown_json  TEXT NOT NULL,
    price_at_search       REAL NOT NULL,
    status_at_search      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_search_results_search ON search_results(search_id);
CREATE INDEX IF NOT EXISTS idx_search_results_apartment ON search_results(apartment_id);

-- The Knowledge Database. Curated, not raw scrape output — see docs/02_Folder_Guide.md data/knowledge_base/.
CREATE TABLE IF NOT EXISTS knowledge_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL,
    key         TEXT NOT NULL,
    value_json  TEXT NOT NULL,
    source      TEXT,
    updated_at  TEXT NOT NULL,
    UNIQUE (category, key)
);

-- Audit trail linking a raw fetch to what it became. See docs/06_Connector_Framework.md /
-- docs/07_Analysis_Engine.md — apartment_id is null until the Analysis Engine resolves the capture.
CREATE TABLE IF NOT EXISTS raw_captures (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id    TEXT NOT NULL REFERENCES platforms(id),
    apartment_id   TEXT REFERENCES apartments(id),
    search_id      TEXT NOT NULL REFERENCES search_requests(id),
    raw_page_path  TEXT NOT NULL,
    captured_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_captures_apartment ON raw_captures(apartment_id);
