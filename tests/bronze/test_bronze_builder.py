"""
Tests for building bronze from raw objects (no network).
"""

import io
import re
from datetime import UTC, date, datetime

import polars as pl
import pytest

from firms_ua.bronze.builder import build_bronze, to_bronze_frame
from firms_ua.common.errors import SchemaError
from firms_ua.common.windows import Window
from firms_ua.datacatalog.bronze import FirmsBronze
from firms_ua.raw.store import write_raw
from firms_ua.storage.base import Storage
from firms_ua.storage.local import LocalStorage

HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
ROW = "50.1,30.2,330.1,0.4,0.4,2024-03-01,0007,N20,VIIRS,n,2.0NRT,290.1,1.2,N\n"
W = Window("VIIRS_NOAA20_NRT", date(2024, 3, 1), 1)
BBOX = (22.1, 44.4, 40.2, 52.4)
ANY = re.compile(r".*")
T0 = datetime(2024, 3, 2, tzinfo=UTC)


def raw_object(raw: Storage, content: str = HEADER + ROW, ts: datetime = T0, window: Window = W):
    """
    Store `content` in raw and return the object.
    """
    return write_raw(raw, window, content.encode(), ts)


def is_built(bronze: Storage, obj) -> bool:
    """
    True if bronze holds a file built from this raw object (the test helper may list; the pipeline itself never does).
    """
    return FirmsBronze.part_exists(bronze, {"source": obj.window.source}, obj.requested_at)


def stores(tmp_path) -> tuple[LocalStorage, LocalStorage]:
    """
    Separate raw and bronze storages, like the two buckets.
    """
    return LocalStorage(tmp_path / "raw"), LocalStorage(tmp_path / "bronze")


def test_build_bronze_from_raw(tmp_path) -> None:
    """
    Bronze is built from a raw object: strings kept, partition by source and acq_date, lineage columns in the file.
    """
    raw, bronze = stores(tmp_path)
    obj = raw_object(raw)
    assert not is_built(bronze, obj)
    (key,) = build_bronze(raw, bronze, obj).keys
    assert key.startswith("firms_viirs/v1/source=VIIRS_NOAA20_NRT/acq_date=2024-03-01/part-")
    assert is_built(bronze, obj)
    again = build_bronze(raw, bronze, obj)  # second run is a no-op
    assert (again.keys, again.rows) == ([], None)

    assert FirmsBronze.file_version(bronze, key) == 1
    stored = pl.read_parquet(io.BytesIO(bronze.get(key)))
    assert stored.columns == FirmsBronze.file_columns()
    assert "source" not in stored.columns
    assert "acq_date" not in stored.columns  # both live in the folder names
    df = FirmsBronze.scan_dataset(bronze).collect()
    FirmsBronze.check(df)
    assert df["acq_date"].to_list() == ["2024-03-01"]  # restored from the folder, still a string
    assert df["acq_time"].to_list() == ["0007"]  # no parsing in bronze
    assert df["day_range"].to_list() == [1]
    assert df["source"].to_list() == ["VIIRS_NOAA20_NRT"]
    assert df["start_date"].to_list() == [date(2024, 3, 1)]
    assert df["type"].to_list() == [None]  # NRT has no type column
    # epoch compare: converting tz-aware values to Python needs tzdata, which Windows lacks
    assert df["requested_at"].dt.epoch("us").to_list() == [int(T0.timestamp() * 1_000_000)]


def test_multi_day_response_splits_by_acq_date(tmp_path) -> None:
    """
    A multi-day response writes one file per acquisition date; each holds only its own rows.
    """
    raw, bronze = stores(tmp_path)
    rows = [ROW, ROW.replace("2024-03-01", "2024-03-02"), ROW.replace("2024-03-01", "2024-03-02").replace(",0007,", ",1021,")]
    obj = raw_object(raw, content=HEADER + "".join(rows), window=Window(W.source, W.start, 5))
    keys = build_bronze(raw, bronze, obj).keys
    assert [k.split("/")[3] for k in keys] == ["acq_date=2024-03-01", "acq_date=2024-03-02"]
    df = FirmsBronze.scan_dataset(bronze).sort("acq_date", "acq_time").collect()
    assert df["acq_date"].to_list() == ["2024-03-01", "2024-03-02", "2024-03-02"]
    assert df["start_date"].unique().to_list() == [W.start]  # the request window is kept in the file
    assert df["day_range"].unique().to_list() == [5]


def test_sp_type_column_is_kept(tmp_path) -> None:
    """
    An SP response with a type column keeps its values (as strings).
    """
    raw, bronze = stores(tmp_path)
    csv = HEADER.replace("daynight", "daynight,type") + ROW.rstrip("\n") + ",0\n"
    build_bronze(raw, bronze, raw_object(raw, content=csv))
    assert FirmsBronze.scan_dataset(bronze).collect()["type"].to_list() == ["0"]


def test_each_raw_object_gets_its_own_bronze_file(tmp_path) -> None:
    """
    A re-fetched window (second raw object) adds a second bronze file; the first stays untouched.
    """
    raw, bronze = stores(tmp_path)
    first = raw_object(raw, ts=T0)
    second = raw_object(raw, ts=T0.replace(hour=1))
    build_bronze(raw, bronze, first)
    assert not is_built(bronze, second)
    build_bronze(raw, bronze, second)
    assert len(bronze.list_keys("firms_viirs/")) == 2
    assert FirmsBronze.scan_dataset(bronze).collect().height == 2


def test_empty_response_writes_no_bronze_file(tmp_path) -> None:
    """
    A header-only response has no acq_date to partition on, so bronze stays empty (raw still holds the response).
    """
    raw, bronze = stores(tmp_path)
    obj = raw_object(raw, content=HEADER)
    result = build_bronze(raw, bronze, obj)
    assert (result.keys, result.rows) == ([], 0)
    assert bronze.list_keys("") == []
    assert raw.exists(obj.key)


def test_unpadded_time_and_empty_frame_keep_schema() -> None:
    """
    Values stay strings as sent, and a header-only CSV gives a valid empty frame.
    """
    ts = datetime(2024, 3, 2, tzinfo=UTC)
    row = ROW.replace(",0007,", ",34,")
    assert to_bronze_frame((HEADER + row).encode(), W, ts)["acq_time"].to_list() == ["34"]
    assert to_bronze_frame(HEADER.encode(), W, ts).height == 0


def test_unknown_column_fails_loudly() -> None:
    """
    An unexpected API column is not silently dropped.
    """
    csv = HEADER.replace("daynight", "daynight,surprise") + ROW.rstrip("\n") + ",x\n"
    with pytest.raises(SchemaError, match="not in DataFrameSchema"):
        to_bronze_frame(csv.encode(), W, datetime(2024, 3, 2, tzinfo=UTC))


def test_missing_required_column_fails_loudly() -> None:
    """
    A response without a required column is rejected.
    """
    with pytest.raises(SchemaError, match="not in dataframe"):
        to_bronze_frame(HEADER.replace("frp,", "").encode(), W, datetime(2024, 3, 2, tzinfo=UTC))


def test_rerun_adds_only_missing_files_and_never_lists_bronze(tmp_path) -> None:
    """
    A partly built response is completed by a rerun, and building works with a bronze storage that cannot list or read.
    """

    class CreateOnly(LocalStorage):
        """
        Like the ingestion identity on the bronze bucket: create only, no list, no read.
        """

        def list_keys(self, prefix: str) -> list[str]:
            """
            Refuse, as a create-only role does.
            """
            raise PermissionError("403 storage.objects.list denied")

        def get(self, key: str) -> bytes:
            """
            Refuse, as a create-only role does.
            """
            raise PermissionError("403 storage.objects.get denied")

        def exists(self, key: str) -> bool:
            """
            Refuse, as a create-only role does.
            """
            raise PermissionError("403 storage.objects.get denied")

    raw = LocalStorage(tmp_path / "raw")
    bronze = CreateOnly(tmp_path / "bronze")
    rows = [ROW, ROW.replace("2024-03-01", "2024-03-02")]
    obj = raw_object(raw, content=HEADER + "".join(rows), window=Window(W.source, W.start, 5))

    first = build_bronze(raw, bronze, obj)
    assert len(first.keys) == 2 and first.rows == 2
    (tmp_path / "bronze" / first.keys[0]).unlink()  # simulate a crash that left only one of the two files
    second = build_bronze(raw, bronze, obj)
    assert second.keys == [first.keys[0]] and second.rows == 2  # only the missing file is written again
    third = build_bronze(raw, bronze, obj)
    assert (third.keys, third.rows) == ([], None)  # everything exists
