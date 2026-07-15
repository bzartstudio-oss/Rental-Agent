"""Search Memory & Comparison Engine (v2.0 Step 3) — see docs/17_Search_Memory.md.

A search is not just a query: it's a complete, permanent record of what was asked,
what happened, and what changed since the last time this location was searched. This
package builds that record (`search_memory_service.record_completed_search`, called
automatically by `RentalResearchAgent.run()`) and reconstructs comparisons/timelines/
statistics from it for reading. Nothing here is ever overwritten — the one exception,
`complete_search_execution`'s `UPDATE`, fills in a run's *own* execution facts once,
not a value that changes over time (see storage/search_memory_repository.py).
"""
