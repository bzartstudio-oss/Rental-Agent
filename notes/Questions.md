# Questions

Open questions that need an answer from the user (or from research) before a decision can be made. This is a working queue, not a duplicate of the "Open Questions" sections scattered across `docs/` — when a question here gets answered, update whichever `docs/` file it blocks and remove it from this list.

- Exact structured shape for `SearchRequest.location`. Blocks: [../docs/04_Search_Request.md](../docs/04_Search_Request.md)
- Exact `status` vocabulary for availability tracking (`available`/`pending`/`delisted`/...). Blocks: [../docs/03_Data_Model.md](../docs/03_Data_Model.md)
- Should a real web-search-API provider (e.g. a licensed search API, with a vendor
  API key) be added as a third `DiscoveryProvider`, and if so which vendor? Only 2
  providers ship in v2.5 Step 13 (`curated_seed`, `manual_url`), both needing zero
  network credentials — a real search-engine-backed provider is a genuine future
  extension, not built this sprint since it needs a vendor/cost/ToS decision this
  mission didn't ask for. Blocks: [../docs/29_Automatic_Platform_Discovery.md](../docs/29_Automatic_Platform_Discovery.md)
- Who curates `discovery/automatic/normalization.py`'s `DOMAIN_ALIASES` dict (empty
  by default), and on what cadence? Real alias pairs (e.g. the same platform under a
  country-specific TLD) are a manual curation decision explicitly deferred this
  sprint. Blocks: [../docs/29_Automatic_Platform_Discovery.md](../docs/29_Automatic_Platform_Discovery.md)
- What concretely does "an explicitly approved supported API/feed integration"
  require organizationally before a `CONNECTOR_MISSING` candidate can be promoted
  without a real connector (legal review? a recorded ToS check? who signs off?) —
  `discovery-cli approve-candidate` currently lets any operator promote a candidate
  into the registry with `connector_available=False`, which is honest but doesn't
  yet enforce any approval workflow beyond "a human ran the command." Blocks: [../docs/29_Automatic_Platform_Discovery.md](../docs/29_Automatic_Platform_Discovery.md)
- When should continuous monitoring (periodic re-discovery) and notifications
  (alerting on newly-supported platforms/locations) be scheduled — both explicitly
  out of scope for v2.5 Step 13 per the mission's own instructions? Blocks: [../docs/29_Automatic_Platform_Discovery.md](../docs/29_Automatic_Platform_Discovery.md)

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
