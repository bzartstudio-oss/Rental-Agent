# Database Notes

Storage/database-specific lessons and decisions for this project. See [Project Learning.md](Project%20Learning.md) for the full index.

## Decisions

- **2026-07-14 — Storage engine: SQLite**, single file at `data/rental_intelligence.db`. Chosen over flat JSON files because the "reproducible and comparable over time" and versioning principles ([../docs/00_Project_Vision.md](../docs/00_Project_Vision.md)) need real relational queries — price trend for one apartment, diffing two search runs — which flat files make painful. Single-machine/single-user in V1, so no server/concurrency requirements pushed toward anything heavier. Zero extra dependency (`sqlite3` is Python standard library). Full schema: [../docs/03_Data_Model.md](../docs/03_Data_Model.md).
- **2026-07-14 — `search_results` is an immutable snapshot table**, not just a join to live `apartments` data. It denormalizes `price_at_search`/`status_at_search` at write time. Without this, an old report's numbers would silently change as new searches update `apartments.current_price` — which breaks "every search is reproducible and comparable over time" the moment you re-read an old report. See [../docs/03_Data_Model.md](../docs/03_Data_Model.md).
- **2026-07-14 — `data/apartments/`, `data/search_history/`, `data/platform_registry/` (scaffolded 2026-07-13) are superseded by SQLite tables.** They're not deleted, just no longer where new code should write — see [../docs/02_Folder_Guide.md](../docs/02_Folder_Guide.md).

## Lessons Learned

None yet.
