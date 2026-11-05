"""
Tests for client validation and bronze writer (no network).
"""

import re
from datetime import UTC, date, datetime

import polars as pl
import pytest
import responses

from firms_ua.bronze import is_ingested, to_bronze_frame, write_bronze
from firms_ua.datacatalog import FirmsBronze, SchemaError
from firms_ua.errors import FirmsError
from firms_ua.firms_client import fetch
from firms_ua.windows import Window

HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
ROW = "50.1,30.2,330.1,0.4,0.4,2024-03-01,0007,N20,VIIRS,n,2.0NRT,290.1,1.2,N\n"
W = Window("VIIRS_NOAA20_NRT", date(2024, 3, 1), 1)
BBOX = (22.1, 44.4, 40.2, 52.4)
ANY = re.compile(r".*")


@responses.activate
def test_fetch_and_write_keeps_bytes(tmp_path) -> None:
    """
    Values survive as strings, lineage is in the file, the key is never written.
    """
    responses.add(responses.GET, ANY, body=HEADER + ROW)
    resp = fetch("SECRETKEY", W, BBOX, max_retries=0)
    assert resp.row_count == 1
    assert "SECRETKEY" not in resp.url_redacted
    out = write_bronze(tmp_path, W, resp, datetime(2024, 3, 2, tzinfo=UTC))
    assert out.suffix == ".parquet"
    assert list(tmp_path.rglob("*.json")) == []  # no manifest
    assert is_ingested(tmp_path, W)

    df = pl.read_parquet(out)
    FirmsBronze.validate(df)
    assert df["acq_time"].to_list() == ["0007"]  # no parsing in bronze
    assert df["day_range"].to_list() == [1]
    assert df["start_date"].to_list() == [date(2024, 3, 1)]
    # epoch compare: converting tz-aware values to Python needs tzdata, which Windows lacks
    assert df["requested_at"].dt.epoch("us").to_list() == [int(datetime(2024, 3, 2, tzinfo=UTC).timestamp() * 1_000_000)]
    assert "SECRETKEY" not in out.read_bytes().decode("latin-1")


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
    csv = HEADER.replace("daynight", "daynight,type") + ROW.rstrip("\n") + ",0\n"
    with pytest.raises(SchemaError, match="unexpected columns"):
        to_bronze_frame(csv.encode(), W, datetime(2024, 3, 2, tzinfo=UTC))


@responses.activate
def test_header_only_is_valid_zero_rows() -> None:
    """
    An empty but valid response has row_count 0.
    """
    responses.add(responses.GET, ANY, body=HEADER)
    assert fetch("K", W, BBOX, max_retries=0).row_count == 0


@responses.activate
def test_bad_body_raises() -> None:
    """
    A 200 with a non-CSV body is an error.
    """
    responses.add(responses.GET, ANY, body="Invalid MAP_KEY")
    with pytest.raises(FirmsError):
        fetch("K", W, BBOX, max_retries=0)


@responses.activate
def test_400_not_retried() -> None:
    """
    A 400 is surfaced immediately.
    """
    responses.add(responses.GET, ANY, status=400, body="bad")
    with pytest.raises(FirmsError, match="HTTP 400"):
        fetch("K", W, BBOX, max_retries=3)
    assert len(responses.calls) == 1
