-- Migration 0003 — Deep Analysis Engine (v2.0 Step 6): extends
-- apartment_analysis_metrics (schema-only since migration 0001) with the columns its
-- richer AnalyzerResult shape needs — Confidence, Evidence, Version, on top of the
-- already-designed Score (metric_value), Source (source_module), and Timestamp
-- (computed_at). Purely additive, all nullable — 0001/0002 untouched.

ALTER TABLE apartment_analysis_metrics ADD COLUMN confidence REAL;
ALTER TABLE apartment_analysis_metrics ADD COLUMN evidence_json TEXT;
ALTER TABLE apartment_analysis_metrics ADD COLUMN analyzer_version TEXT;
