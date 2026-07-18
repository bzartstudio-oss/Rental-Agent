-- Migration 0012 — Provider API Call Budget (v2.7 Milestone 2.7.2, RentCast
-- Resilience). One new table, no existing table modified — 0001-0011 untouched.
--
-- One row per (provider_id, period_key), `period_key` a UTC "YYYY-MM" string.
-- A new calendar month naturally starts a fresh row (call_count=0) the first
-- time that month's budget is checked — no explicit reset job needed, the
-- previous month's row is simply left in place as a historical record, the
-- same "append rather than overwrite across periods" bias
-- `saved_search_versions`/`notification_preference_versions` already follow.
-- `monthly_limit` is captured per-period (not read fresh from config on every
-- check) so a mid-month configuration change never retroactively changes how
-- much of the current period was already considered "the budget."
CREATE TABLE IF NOT EXISTS provider_call_budget (
    provider_id   TEXT    NOT NULL,
    period_key    TEXT    NOT NULL,
    call_count    INTEGER NOT NULL DEFAULT 0,
    monthly_limit INTEGER NOT NULL,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL,
    PRIMARY KEY (provider_id, period_key)
);
