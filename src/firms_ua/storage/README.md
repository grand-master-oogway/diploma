# storage

Where bytes live. One `Storage` per medallion layer; objects are never overwritten.

- `base.py`: the `Storage` interface (`put_new`, `get`, `exists`, `list_keys`, `uri`, `polars_options`).
- `local.py`: `LocalStorage`, a folder on disk (development and tests).
- `gcs.py`: `GcsStorage`, a GCS bucket (Application Default Credentials, `if_generation_match=0`).
- `factory.py`: `open_storage(root, layer, project)` picks the backend: a local folder, or `gs://<prefix>` with the layer appended.
