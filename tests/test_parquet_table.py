"""
Tests for ParquetTable: versioned path, Hive partitions, unique files, metadata.
"""

import io
from datetime import UTC, date, datetime

import pandera.polars as pa
import polars as pl
import pytest

from firms_ua.datacatalog_core.parquet_table import ParquetTable
from firms_ua.errors import SchemaError
from firms_ua.storage import LocalStorage, Storage


class Events(ParquetTable):
    """
    Demo table partitioned by day.
    """

    value: pl.Int64
    day: pl.Date = pa.Field(description="partition")

    class Config:
        """
        Identity and layout.
        """

        name = "silver.events"
        metadata = {"version": 2, "partition_by": ("day",)}


T1 = datetime(2026, 1, 1, 10, tzinfo=UTC)
T2 = datetime(2026, 1, 1, 11, tzinfo=UTC)


def frame() -> pl.DataFrame:
    """
    Two partitions, three rows.
    """
    return pl.DataFrame({"value": [1, 2, 3], "day": [date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 2)]})


def test_versioned_hive_layout_and_file_metadata(store: Storage) -> None:
    """
    Files go to <table>/v<version>/day=<value>/, partition columns are not in the files, version is in metadata.
    """
    keys = Events.write(frame(), store, T1)
    assert sorted(keys) == [
        "events/v2/day=2026-01-01/part-20260101T100000000000Z.parquet",
        "events/v2/day=2026-01-02/part-20260101T100000000000Z.parquet",
    ]
    assert pl.read_parquet(io.BytesIO(store.get(keys[0]))).columns == ["value"]
    assert Events.file_version(store, keys[0]) == 2
    assert Events.file_columns() == ["value"]
    assert Events.table_layer() == "silver"


def test_scan_restores_partition_columns(local_store: LocalStorage) -> None:
    """
    Reading with hive partitioning gives back the declared columns, order and dtypes.
    """
    Events.write(frame(), local_store, T1)
    out = Events.scan_dataset(local_store).sort("value").collect()
    assert out.columns == ["value", "day"]
    assert out.schema == Events.polars_schema()
    assert out["day"].to_list() == [date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 2)]


def test_rewrite_adds_files_never_overwrites(store: Storage) -> None:
    """
    A second write with another timestamp adds files; the same timestamp is refused.
    """
    first = Events.write(frame(), store, T1)
    Events.write(frame(), store, T2)
    assert all(store.exists(k) for k in first)
    assert len(store.list_keys("events/")) == 4
    with pytest.raises(FileExistsError):
        Events.write(frame(), store, T1)


def test_invalid_frame_writes_nothing(store: Storage) -> None:
    """
    A frame that fails validation leaves the storage untouched.
    """
    bad = frame().with_columns(value=pl.col("value").cast(pl.String))
    with pytest.raises(SchemaError):
        Events.write(bad, store, T1)
    assert store.list_keys("") == []


def test_empty_frame_needs_partition_values(store: Storage) -> None:
    """
    An empty frame is written only when the partition is given explicitly.
    """
    empty = frame().clear()
    with pytest.raises(ValueError, match="partition_values"):
        Events.write(empty, store, T1)
    (key,) = Events.write(empty, store, T1, partition_values={"day": date(2026, 1, 3)})
    assert "/day=2026-01-03/" in key
    assert pl.read_parquet(io.BytesIO(store.get(key))).height == 0
    assert Events.part_exists(store, {"day": date(2026, 1, 3)}, T1)
    assert not Events.part_exists(store, {"day": date(2026, 1, 3)}, T2)


def test_scan_without_files_raises(local_store: LocalStorage) -> None:
    """
    Scanning a table with no data fails clearly.
    """
    assert not Events.has_files(local_store)
    with pytest.raises(FileNotFoundError):
        Events.scan_dataset(local_store)
