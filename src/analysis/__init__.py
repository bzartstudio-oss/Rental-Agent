"""The Deep Analysis Engine (v2.0 Step 6) — see docs/19_Analysis_Engine.md.

Transforms already-collected apartment listings into rich, structured intelligence —
walking distance, nearby amenities, composite location/convenience/lifestyle/
accessibility scores. Never touches the original listing data (`Apartment` is never
mutated); every result is stored separately in `apartment_analysis_metrics`, append-only.

Evidence-based, not predictive: every analyzer either computes a real score from real
data (curated reference facts, real coordinate math) or honestly reports "no evidence
yet" (`score=None`) — there is no AI, no machine learning, no inference anywhere in
this package.
"""
