-- Migration 0006 — Geographic Intelligence Engine (v2.5 Step 10): records what one
-- `GeographicEngine.enrich()` call actually computed for one apartment (provider,
-- calculation method, confidence, a summary of distances/nearby results) — mirrors
-- `filter_execution_history` (migration 0005)'s exact "record what one engine run
-- produced" shape, applied to geo enrichment instead of filtering. Purely additive —
-- 0001-0005 untouched.

CREATE TABLE IF NOT EXISTS geo_enrichment_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    apartment_id        TEXT NOT NULL,
    search_id           TEXT REFERENCES search_requests(id),
    provider_id         TEXT NOT NULL,
    calculation_method  TEXT NOT NULL,
    summary_json        TEXT NOT NULL,
    confidence          REAL,
    recorded_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_geo_history_apartment ON geo_enrichment_history(apartment_id);
CREATE INDEX IF NOT EXISTS idx_geo_history_search ON geo_enrichment_history(search_id);
