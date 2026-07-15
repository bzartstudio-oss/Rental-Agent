# 07 — Analysis Engine

Status: V1.0 core write sequence live in code. **v2.0 Step 2 (2026-07-14): extended
Apartment History and Image Change Detection are now live** — see "Write Sequence" and
"Image Change Detection" below, both updated to describe the actual implementation.
**Deep Analysis Engine remains designed only** (Step 7, blocked on an unmade vendor
decision — see "Open Questions").

## Goal (unchanged)

Take the raw, inconsistent output from each connector ([06_Connector_Framework.md](06_Connector_Framework.md)) and turn it into normalized `Apartment` records matching [03_Data_Model.md](03_Data_Model.md), while writing history rather than overwriting.

## Pipeline within the Analysis Engine

Sub-steps, each a separate module (see [02_Folder_Guide.md](02_Folder_Guide.md)):

1. **`normalizer.py`** (v1.1, live) — `RawListing` → `Apartment`-shaped data. **v2.0
   Step 2, live:** also normalizes `description` (new field — see
   [03_Data_Model.md](03_Data_Model.md) `apartments.description`; `connectors/base.py`'s
   `RawListing` gained a matching `description` field).
2. **`deduplicator.py`** (v1.1, live) — within-platform identity lookup, unchanged.
3. **`change_detector.py`** (v1.1, live) — compares price/status only, **unchanged by
   v2.0 Step 2.** Deliberate deviation from this doc's original plan (which proposed
   extending this module with `title_changed`/`description_changed`): comparison logic
   for every new v2.0 trackable field (title, description, coordinates, images, listing
   presence) was consolidated instead in the new `src/history/comparison.py`, so that
   every comparison — not just the two new scalar ones — produces the same structured
   `Change` object (see [15_Agent_Architecture.md](15_Agent_Architecture.md)-adjacent
   `src/history/models.py`). Price/status keep using `change_detector.py`'s booleans
   unchanged, since `engine.py`'s decision to write to their pre-existing dedicated
   history tables didn't need to change. See `learning/architecture_notes.md`.
4. **`enricher.py`** (v1.1, live, minimal) — becomes the **Deep Analysis Engine** in
   v2.0, see below. v1.1's one function (`price_per_sqft`, computed-on-read) is kept
   as-is; v2.0 adds new, separately-computed metrics alongside it. **Not touched by
   Step 2.**
5. **`engine.py`** (v1.1, live) — the write-sequence composition. **v2.0 Step 2, live:**
   also calls the Apartment History Engine (`src/history/history_service.py`) and Image
   Change Detection as part of the same per-listing sequence (see updated sequence
   below). The Deep Analysis Engine's metric computation is **not yet called** — Step 7.

## Write Sequence (per listing) — v2.0 Step 2, live

```
RawListing
  → normalize (now includes description)
  → apartment already exists (by platform_id + platform_listing_id)?
       NO  → INSERT into apartments (first_seen_at = now)
             INSERT initial apartment_price_history + apartment_availability_history rows
             INSERT initial apartment_change_log rows for title/description (old_value = NULL)
             download images → INSERT apartment_images (is_current = 1) + apartment_image_events ("added") rows
       YES → UPDATE apartments.last_seen_at, current_price, current_status (existing);
             UPDATE apartments.title, description (new: update_apartment_details)
             IF price changed    → INSERT apartment_price_history row
             IF status changed   → INSERT apartment_availability_history row
             IF title changed    → INSERT apartment_change_log row (field_name="title")
             IF description changed → INSERT apartment_change_log row (field_name="description")
             → diff current apartment_images against this observation's image_urls (see
               "Image Change Detection" below); INSERT apartment_image_events for any
               added/removed images
  → Deep Analysis Engine: compute/refresh applicable metrics → INSERT apartment_analysis_metrics rows
     — NOT YET CALLED (Step 7, blocked on a vendor decision; see Open Questions)
```

Everything added in v2.0 follows the same "only write on actual change" discipline as
price/status in v1.0 — re-observing an unchanged apartment still writes nothing new to
`apartment_change_log`/`apartment_image_events`, exactly like it already writes nothing
new to the history tables today. Verified for real against the actual dev database
(not just tests): editing `demo_platform`'s fixture title, re-running the CLI, and
confirming a real `apartment_change_log` row appeared with the correct
old/new values — then reverting the fixture and re-running again, confirming a *second*
row recorded the reversion without disturbing the first (append-only, proven live).

One nuance not in the original plan: `apartment_image_events.search_id` is `NOT NULL`
(an image event is always tied to the run that detected it), so logging is skipped —
not the download/flip itself — when `process_listing()` is called without a `search_id`
(only happens in direct unit tests; the real `RentalResearchAgent` always has one).

## Image Change Detection (v2.0 Step 2, live)

Requirement: "Detect image changes between executions." On a re-observation:

1. Load the apartment's current `apartment_images` rows where `is_current = 1`.
2. Compare their `source_url` set against this observation's `RawListing.image_urls`.
3. For any URL present now but not before: download it, `INSERT apartment_images`
   (`is_current = 1`), `INSERT apartment_image_events` (`event = "added"`).
4. For any URL present before but not now: `UPDATE apartment_images SET is_current = 0`
   (never delete the row — the image stays downloaded and queryable), `INSERT
   apartment_image_events` (`event = "removed"`).

This is the same append-only discipline as everything else — a "removed" image is still
on disk and still in `apartment_images`, just flagged as no longer part of the current
listing. Implemented as one function (`analyzers/engine.py::_sync_images`) used for
*both* branches, not two separate code paths: a brand-new apartment has no current
images yet, so every URL naturally comes back "added," in original listing order —
identical behavior to V1.0, just reached via the same diff logic re-observation uses.

Two more comparison methods exist in `src/history/comparison.py` but aren't wired into
this write sequence yet, both deliberately: `compare_coordinates` (no connector or
`normalizer.py` populates `latitude`/`longitude` today — waits on the Deep Analysis
Engine, Step 7) and `compare_presence` (`listing_removed`/`listing_returned` — requires
knowing whether an apartment was genuinely absent from a platform's full result set this
run, which is Search Memory's job, Step 3, not built yet). Both are implemented and
unit-tested standalone so they're ready the moment their real trigger exists.

## Deep Analysis Engine (v2.0, designed — not yet implemented)

Requirement 6 — the Research Agent doesn't stop at scraping. New modules alongside the
existing four:

- **`analyzers/distance.py`** — walking distance, public transport time/score, from the
  apartment's `latitude`/`longitude` to whatever reference point(s) a `SearchRequest`
  cares about (see [04_Search_Request.md](04_Search_Request.md) "The Proximity/Score
  Dependency"). Requires a geocoding/routing data source — *which one is an
  implementation-time decision, not resolved here* (could be a paid API, an open dataset,
  or a knowledge-base-backed approximation; whichever is chosen must respect the same
  "no live scraping of a commercial site without checking ToS" caution already applied to
  connectors elsewhere in this project).
- **`analyzers/nearby.py`** — counts/distances to nearby amenities (supermarkets,
  universities, gyms, pharmacies, hospitals) — same external-data-source caveat as above.
- **`analyzers/scores.py`** — composite scores (`lifestyle_score`, `convenience_score`,
  `location_score`) computed from the outputs of `distance.py`/`nearby.py` plus
  `knowledge_entries` (e.g. a neighborhood safety/noise benchmark). "Future environmental
  indicators" (air quality, flood risk, etc.) slot in here later as more `metric_name`
  values — no schema change needed, per `apartment_analysis_metrics`'s generic design.

Every computed value is written to `apartment_analysis_metrics`
([03_Data_Model.md](03_Data_Model.md)), tagged with which module computed it and which
search triggered the computation — never held only in memory, and never silently
overwritten if recomputed later (a new row, not an update — same versioning principle as
everything else in this system).

**Resolves the v1.0 open question** ("are enriched fields stored or computed on read?"):
**both**, split by kind — `price_per_sqft` (a pure function of already-stored
`current_price`/`sqft`, nothing external) stays computed-on-read, unchanged. Everything
that requires external data or nontrivial computation (distance, transit, nearby-amenity
counts, composite scores) is stored in `apartment_analysis_metrics`, because recomputing
it on every read would be wasteful and because the versioned history of *how a location
score changed over time* is itself valuable data, not just a cache.

## Cross-Platform De-Duplication (V2, unchanged)

Still not built — see v1.0 reasoning, unaffected by this upgrade.

## Open Questions

- Which geocoding/transit/nearby-amenity data source to use for the Deep Analysis Engine — a real product/vendor decision, not resolved by this architecture pass.
- What counts as a "changed enough" difference for `description` (a single typo fix
  shouldn't spam `apartment_change_log`) — carried over from v1.0's identical open
  question about price, now also applies to free-text fields where "changed" is fuzzier
  than a numeric comparison. Proposed: exact string inequality for v2.0 (simplest,
  consistent with how title/price already work), revisit if it proves too noisy in
  practice.
