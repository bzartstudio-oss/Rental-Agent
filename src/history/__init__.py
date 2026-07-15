"""Apartment History Engine (v2.0 Step 2) — see docs/07_Analysis_Engine.md "Write
Sequence" and docs/03_Data_Model.md "The Versioning Principle, Formalized".

Every apartment is a timeline, not a row that gets overwritten. This package turns a
normalized observation into structured `Change` objects (models.py, comparison.py) and
appends them to history (history_service.py), plus reconstructs timelines/prior states
for reading. It never overwrites or deletes a history row.
"""
