# 07 — Analysis Engine

Status: V1.0 design confirmed (2026-07-14) — this is where Principles 1 and 3 (never lose information, historical versions) actually get implemented as writes.

## Goal

Take the raw, inconsistent output from each connector ([06_Connector_Framework.md](06_Connector_Framework.md)) and turn it into normalized `Apartment` records matching [03_Data_Model.md](03_Data_Model.md), while writing history rather than overwriting.

## Pipeline within the Analysis Engine

Four sub-steps, each a separate module (see [02_Folder_Guide.md](02_Folder_Guide.md)):

1. **`normalizer.py`** — `RawListing` → `Apartment`-shaped data (not yet written to the database). Resolves currency/period normalization, structures the address if possible.
2. **`deduplicator.py`** — checks whether this listing already exists (same `platform_id` + `platform_listing_id` → same `apartments` row) or is a new one. **V1 scope: within-platform only.** Cross-platform de-duplication (the same physical apartment on two sites) is explicitly V2 — see "Cross-Platform De-Duplication (V2)" below.
3. **`change_detector.py`** — for an existing apartment, compares the newly normalized price/status against `apartments.current_price`/`current_status`. Only if they differ does it write a new row to `apartment_price_history` / `apartment_availability_history` — this is what keeps the history tables from filling up with a redundant row on every single search that happens to re-observe an unchanged listing.
4. **`enricher.py`** — derived fields computed once, here, rather than per-connector (so the calculation is identical regardless of source platform): e.g. price-per-sqft, distance from a reference point. Consults `knowledge_entries` for anything that needs curated reference data (e.g. neighborhood benchmarks).

## Write Sequence (per listing)

```
RawListing
  → normalize
  → apartment already exists (by platform_id + platform_listing_id)?
       NO  → INSERT into apartments (first_seen_at = now); INSERT initial apartment_price_history + apartment_availability_history rows
       YES → UPDATE apartments.last_seen_at, current_price, current_status
             IF price changed → INSERT apartment_price_history row
             IF status changed → INSERT apartment_availability_history row
  → download images via collectors/image_collector.py → INSERT apartment_images rows
  → enrich → (fields live on the apartments row or are computed on demand — TBD, see below)
```

This sequence is what "every search updates permanent databases" (Principle 2) means concretely — it's not optional post-processing, it's the only way listing data ever enters the database.

## Cross-Platform De-Duplication (V2)

Not built in V1.0 (see Non-Goals in [00_Project_Vision.md](00_Project_Vision.md)). The `apartments.merged_into_id` column already exists in the schema (see [03_Data_Model.md](03_Data_Model.md)) specifically so this can be added later without a migration: a future de-duplication pass would set `merged_into_id` on the duplicate row rather than deleting it (Principle 1 — never lose information, even a listing later identified as a duplicate keeps its own observation history).

## Open Questions

- Are enriched fields (price-per-sqft, etc.) stored as columns on `apartments`, or computed on read? Leaning toward computed-on-read for anything that's a pure function of other stored fields (avoids yet another place that can go stale), stored only for anything that requires external lookups (e.g. distance to a point that isn't part of the request itself). To confirm once the first enrichment rule is actually needed.
- What counts as a "changed enough to be a new history row" price difference — any change, or a minimum delta to avoid noise from rounding differences across platforms?
