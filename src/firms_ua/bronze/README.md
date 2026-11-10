# bronze

Raw CSV to string-typed Parquet in Hive partitions (`source`, `acq_date`), never overwritten.

- `builder.py`: `to_bronze_frame` (parse, add lineage, validate against `FirmsBronze`) and `build_bronze` (one raw object to one file per
  acquisition date). The table definition itself lives in `datacatalog/bronze.py`.
