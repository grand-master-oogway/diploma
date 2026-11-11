# tests/orchestration

Tests for the Dagster layer: pure planning (`test_planning.py`) and end-to-end in-process runs of `firms_raw` -> `firms_bronze` with
local storage and a fake fetcher (`test_assets.py`). No network, no Dagster instance on disk.
