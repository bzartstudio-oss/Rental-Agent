# Questions

Open questions that need an answer from the user (or from research) before a decision can be made. This is a working queue, not a duplicate of the "Open Questions" sections scattered across `docs/` — when a question here gets answered, update whichever `docs/` file it blocks and remove it from this list.

- Exact structured shape for `SearchRequest.location`. Blocks: [../docs/04_Search_Request.md](../docs/04_Search_Request.md)
- Exact `status` vocabulary for availability tracking (`available`/`pending`/`delisted`/...). Blocks: [../docs/03_Data_Model.md](../docs/03_Data_Model.md)

## Answered

- ~~Which platform/data source should the first connector target?~~ **RentCast**
  (2026-07-15) — a real, developer-facing REST API with self-service auth, a free
  tier, and published Terms of Use permitting this kind of programmatic access;
  verified by live lookup rather than chosen from the 6 previously-catalogued
  scraping-prohibited platforms (Zillow, Apartments.com, Rightmove, Idealista,
  Fotocasa, ImmoScout24), all of which remain `connector_available = False`. See
  [../docs/20_First_Production_Connector.md](../docs/20_First_Production_Connector.md).
- ~~What rental type(s) does the agent need to support?~~ **Residential apartments** (2026-07-13). See [../docs/00_Project_Vision.md](../docs/00_Project_Vision.md), [../docs/03_Data_Model.md](../docs/03_Data_Model.md).
- ~~What output format does a report need?~~ **HTML only for V1.0**, since structured data already lives durably in SQLite regardless (2026-07-14). See [../docs/09_Report_System.md](../docs/09_Report_System.md).
- ~~Storage format: JSON files vs. database?~~ **SQLite** (2026-07-14). See [../learning/database_notes.md](../learning/database_notes.md).
- ~~Should `data/rental_intelligence.db`/`data/media/`/`data/raw_pages/` be gitignored or committed?~~ **Gitignored**, same treatment as `output/*` — generated artifacts, not source-controlled inputs (2026-07-14). See `.gitignore`.
