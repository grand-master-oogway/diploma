# datacatalog_core

Shared machinery for table definitions. No concrete tables live here (those are in `datacatalog/`).

- `parquet_table.py`: `ParquetTable`, a pandera `DataFrameModel` for Parquet tables (strict, ordered validation).
  - Declared in `Config`: `name = "<layer>.<table>"` and `metadata = {"version": N, "partition_by": (...)}`.
  - Layout inside the layer's storage: `<table>/v<N>/<key>=<value>/.../part-<UTC timestamp>.parquet`. Partition columns live in the folder names, not in the files; the version is also stored in each file's Parquet metadata.
  - `check(df)` raises the project's `SchemaError` listing every mismatch; `write(df, store, requested_at)` validates, then adds one new file per partition (never overwrites); `replace_partition(df, store, written_at, partition_values)` writes a new file for one partition, reads it back and validates it, then deletes the partition's older files (silver/gold; idempotent, not atomic); `part_files(store, partition_values)` lists a partition's files; `scan_dataset(store)` reads everything back with partition columns restored; `file_version(store, key)` reads the version from a file.
  - Helpers: `column_names()`, `file_columns()`, `partition_columns()`, `polars_schema()`, `columns_with_metadata(key)`, `dataset_prefix()`.
- `bigquery.py`: BigQuery types and Hive key spec derived from a `ParquetTable` (`external_table_spec`), so BigQuery sees the same types as Polars.

Do not name a column like a method above (for example `check`, `write`, `scan_dataset`): the column would shadow it.
