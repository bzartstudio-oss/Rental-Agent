-- Migration 0004 — First Production Connector (v2.0 Step 7): adds `currency` and
-- `property_type` to `apartments`. Neither existed before because every prior
-- connector (demo_platform, demo_platform_two) is a fixed-currency, single-property-
-- type reference fixture with no real data to populate them from. RentCast (the first
-- real connector) genuinely reports both, so they earn a real, additive schema slot —
-- 0001/0002/0003 untouched. Both nullable: existing rows backfill NULL, meaning
-- "unknown," never a fabricated default.

ALTER TABLE apartments ADD COLUMN currency TEXT;
ALTER TABLE apartments ADD COLUMN property_type TEXT;
