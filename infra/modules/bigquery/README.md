# bigquery

Makes the lake queryable from BigQuery without copying data: BigLake external tables over the Hive-partitioned Parquet
files of bronze and silver.

- `google_bigquery_connection` (cloud resource): its service account gets `roles/storage.objectViewer` on the bronze and
  silver buckets. People never need bucket access; they need `roles/bigquery.dataViewer` on the datasets and
  `roles/bigquery.jobUser` on the project (both granted to `analyst_members`).
- Datasets `<env>_<layer>` (for example `dev_silver`), in the buckets' region (BigQuery requires the same location).
- One external table per file in `schemas/`. Those files are generated from the Python table definitions:
  run `firms-ua bq-schemas` after changing a table (a test fails if they are stale). Each holds the file columns'
  BigQuery types, the Hive key spec (for example `{acq_date:DATE}`) and the versioned path (`firms_detections/v1`).
  Partition columns come from folder names; `ignore_auto_generated_schema` keeps them out of the Terraform diff.
- Metadata caching is off, so every query lists the current files. A new table version (`v2`) is a new path: regenerate
  the specs and apply.
