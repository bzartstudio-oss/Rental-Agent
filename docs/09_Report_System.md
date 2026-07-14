# 09 — Report System

Status: V1.0 design confirmed (2026-07-14) — HTML only for V1.

## Goal

Turn the `search_results` rows for one `search_id` ([03_Data_Model.md](03_Data_Model.md)) into an HTML report — the actual deliverable a person reads.

## Report Format: HTML (V1.0 decision)

V1.0 ships the HTML Report Generator only (per the V1.0 scope in [00_Project_Vision.md](00_Project_Vision.md)) — not a separate structured-data export. This is sufficient because the structured data already durably exists in `data/rental_intelligence.db`; the HTML report is a *view* over `search_results`, not the only place the data lives. A CSV/JSON export is a plausible small V1.1 addition (querying `search_results` for one `search_id` is already all the logic it needs) but isn't required to satisfy any of the 7 core principles, so it's not in V1.0 scope.

## Module

`services/report_generator.py`, using Jinja2-style templates in `services/report_templates/` (*proposal, not yet locked in* — see [02_Folder_Guide.md](02_Folder_Guide.md)). Absorbs/replaces the legacy `src/reports/` and `src/exporters/` folders (see reconciliation table in [02_Folder_Guide.md](02_Folder_Guide.md)).

## Report Contents

For a given `search_id`:

- The `SearchRequest` criteria it was run with (so the report is self-describing — Principle 4, reproducible/comparable)
- Ranked apartments, in order, each showing:
  - Title, price, bedrooms/bathrooms/sqft, address
  - **Original listing URL** (Principle: "original listing URLs") — a direct link back to the source
  - Images (Principle: "image extraction") — pulled from `apartment_images`
  - Score, and the score breakdown (Principle 5 traceability — see [08_Ranking_System.md](08_Ranking_System.md))
  - **Price/availability history** for that apartment (Principles: "price history", "availability tracking") — pulled from `apartment_price_history` / `apartment_availability_history`, so a report shows not just "current price" but the trend
- Generation timestamp

## Where Reports Are Saved

`output/` (see [02_Folder_Guide.md](02_Folder_Guide.md)) — one HTML file per `search_id`, e.g. `output/<search_id>.html`. Never committed as a fixed input; already excluded from git via `.gitignore` except for the placeholder.

## Open Questions

- Does a report need to be shareable outside this repo (e.g. emailed to a client) — if so, images should be embedded (base64) or the report shipped alongside its `data/media/` files, rather than assuming a viewer has local filesystem access to relative image paths.
