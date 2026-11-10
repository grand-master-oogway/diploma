# datacatalog

Table definitions only: one class per table, one file per layer. Nothing else belongs here.

- `bronze.py`: `FirmsBronze`, all API columns as strings (`type` is optional: SP only, null in NRT), then lineage columns (`day_range`, `requested_at`, `source`, `start_date`). Hive partitions: `source` and `acq_date` (stored in folder names, not in the files).
- `ingestion_log.py`: `IngestionLog` (`raw.ingestion_log`), one row per step attempt per request window; stored in the raw bucket, partitioned by `source`.
- `silver.py`, `gold.py`: filled when those layers are built.

A table is a subclass of `ParquetTable` (see `datacatalog_core/`): Polars-typed annotated columns plus `Config.name` and `Config.metadata` (version, partitions). Columns are non-nullable unless declared with `nullable=True`; `Field(description=...)` documents a column and `Field(metadata={...})` tags it.
