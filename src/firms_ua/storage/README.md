# storage

Where bytes live. One `Storage` per medallion layer; objects are never overwritten (silver and gold may delete whole old
partition files after writing their replacement; raw and bronze identities cannot delete).

- `base.py`: the `Storage` interface (`put_new`, `get`, `delete`, `exists`, `list_keys`, `uri`, `polars_options`).
- `local.py`: `LocalStorage`, a folder on disk (development and tests).
- `gcs.py`: `GcsStorage`, a GCS bucket (Application Default Credentials, `if_generation_match=0`).
- `factory.py`: `open_storage(root, layer, project)` picks the backend: a local folder, or `gs://<prefix>` with the layer appended.
