# datacatalog

One place that says what every table looks like.

- `base.py`: `Column` (name, Polars dtype, description, nullable) and `Table` (layer, columns, partition columns, `schema()`, `validate(df)`).
- `bronze.py`: `FirmsBronze`, all API columns as strings plus lineage columns.
- `silver.py`, `gold.py`: filled when those layers are built. A new table is a subclass of `Table` that declares `name`, `layer`, `columns`, `partition_by`.

Writers call `Table.validate(df)` before writing, so the code can never produce a different layout than the one declared here. Bump `version` when columns change.
