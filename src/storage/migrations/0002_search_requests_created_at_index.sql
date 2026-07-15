-- Migration 0002 — index search_requests(created_at).
--
-- Found during the v2.0 Step 4.5 architecture review: search_requests had no index
-- beyond its primary key, but storage/search_memory_repository.py's
-- find_previous_search() (WHERE created_at < ? ORDER BY created_at DESC) and
-- get_search_history() (ORDER BY created_at DESC) both scan and sort the whole table
-- on every call — and find_previous_search() runs on every single completed search
-- (src/search_memory/search_memory_service.py::record_completed_search). Invisible at
-- today's row counts; would degrade as real search history accumulates. Purely
-- additive — no existing column, table, or row changes.

CREATE INDEX IF NOT EXISTS idx_search_requests_created_at ON search_requests(created_at);
