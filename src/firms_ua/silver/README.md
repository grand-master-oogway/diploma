# silver

Bronze (string columns, one file per source, day and response) -> one typed table per UTC day, the same schema for SP
and NRT, with derived columns and flags. Questionable rows are flagged, not deleted: filtering by flags is a gold
parameter. Silver is rebuilt from bronze; every write replaces a whole day.

Pure functions only (Polars in, Polars out). The Dagster wrappers are in `orchestration/silver_assets.py`, the table
definitions in `datacatalog/silver.py`.

## Tables

- `silver.firms_detections` (`FirmsSilver`), partitioned by UTC `acq_date`. Columns and their origin: see the class.
  Highlights: one UTC `acq_time` (FIRMS `acq_date` + `acq_time` padded to HHMM); `acq_date_kyiv` for gold's day;
  `product` (sp/nrt) and `collection` from `version`; `satellite` from the source id; `h3_r9` and its parent `h3_r7`;
  `pass_id`; `in_ukraine` and `border_distance_km`; `is_persistent_hotspot`; `is_preferred`;
  `flag_invalid_brightness` (`bright_ti4` or `bright_ti5` <= 0 K, a FIRMS fill value). Boundary name and sha256
  and the run id are in each file's Parquet metadata.
- `silver.h3_r9_daily_activity` (`H3DailyActivity`): preferred detections per H3 r9 cell and UTC day, the input of
  the hotspot flag. Built from bronze, not from silver, so the flag creates no dependency cycle.

## Steps (one UTC day)

| Module | Step |
|---|---|
| `resolve.latest_responses` | Keep the latest response per (source, day). A union per detection would keep detections FIRMS removed later. |
| `parse.parse_bronze` | Strict typing: an empty required value, an unknown label (`labels.py`) or a value that does not parse fails the run. `detection_id` = SHA-256 (32 hex) of source, latitude, longitude, date and padded time as sent. |
| `resolve.drop_repeats` | Drop exact `detection_id` repeats, counted. |
| `cells.add_cells` | `h3_r9` from the pixel center, `h3_r7` as its parent. The center is not the fire's location. |
| `border.locate` | `in_ukraine`, `border_distance_km` in EPSG:3035. Rows farther than `FIRMS_BORDER_BUFFER_KM` (30) outside are dropped, counted. |
| `resolve.mark_preferred` | Day-level rule per satellite: SP rows if that day has SP, else NRT. Different satellites are never deduplicated. |
| `build.flag_invalid_brightness` | Flag brightness <= 0 K (FIRMS sends `bright_ti4` = 0 for a few rows); the row is kept. |
| `passes.assign_passes` | New pass after a gap > 20 min; id = satellite + first time of the pass. Uses the last hour of the previous day so a pass crossing midnight keeps one id. |
| `hotspots` | Cell active on >= `MIN_ACTIVE_DAYS` (provisional 30) of days D-365..D-1. Past only, so no leakage into gold; the first year has partial history. |
| `build` | `prepare_day` (the steps up to the preference) and `finish_day` (passes, hotspots, run id, column order, sorted). `DayCounts` reconciles: bronze rows = superseded + duplicates + outside buffer + kept. |
| `quality` | Checks of a built day (see below). |

## Quality checks (Dagster asset checks on `firms_silver`)

Blocking (a failing day is not written and the run fails): `keys_not_null`, `unique_ids`, `in_partition`,
`value_ranges` (scan/track 0.25-1.0 km, ti4 200-400 K, ti5 150-400 K, frp >= 0; brightness skipped on rows with
`flag_invalid_brightness`; checked against the bronze profile in `docs/silver_findings.json`),
`reconciliation`. Warnings: `satellite_gaps` (a covered satellite with 0 rows while another has >= 50),
`preferred_jump` (preferred share moves > 0.5 from the previous day in the run).

## Known limits

- Replacing a day is not atomic: for a moment a reader can see the old and the new file (GCS has no rename).
- Changing an old bronze day (for example an SP catch-up) rebuilds up to 365 later silver days (hotspot window).
- The boundary includes the 12 nmi territorial sea (OSM-derived): near-shore sea points count as `in_ukraine`.
- `MIN_ACTIVE_DAYS` = 30 marks about 170-310 H3 r9 cells per year (out of 110k-215k with any detection), per
  `docs/silver_findings.json`.
- No pixel-level NRT-SP matching: bronze has no SP/NRT overlap today (SP up to 2026-07-31, NRT after).

`boundary/` holds the Ukraine polygon; see its README.
