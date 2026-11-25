"""
Typing bronze strings: time, labels, strict parsing, ids.
"""

from datetime import UTC, date, datetime

import polars as pl
import pytest

from bronze_factory import bronze, nrt
from firms_ua.common.errors import DataError
from firms_ua.silver.parse import parse_bronze


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("34", datetime(2025, 7, 15, 0, 34, tzinfo=UTC)),
        ("7", datetime(2025, 7, 15, 0, 7, tzinfo=UTC)),
        ("2359", datetime(2025, 7, 15, 23, 59, tzinfo=UTC)),
    ],
)
def test_acq_time_is_padded_and_utc(raw: str, expected: datetime) -> None:
    """
    Acq time is padded and utc.
    """
    out = parse_bronze(bronze({"acq_time": raw}))
    assert out["acq_time"].to_list() == [expected]


@pytest.mark.parametrize(
    ("day", "hhmm", "kyiv_day"),
    [
        ("2025-07-15", "2059", date(2025, 7, 15)),  # summer, UTC+3: 23:59 Kyiv
        ("2025-07-15", "2100", date(2025, 7, 16)),  # 00:00 Kyiv
        ("2025-01-15", "2159", date(2025, 1, 15)),  # winter, UTC+2: 23:59 Kyiv
        ("2025-01-15", "2200", date(2025, 1, 16)),
        ("2025-03-30", "0058", date(2025, 3, 30)),  # the DST switch day
    ],
)
def test_kyiv_date_follows_daylight_saving(day: str, hhmm: str, kyiv_day: date) -> None:
    """
    Kyiv date follows daylight saving.
    """
    out = parse_bronze(bronze({"acq_date": day, "acq_time": hhmm}))
    assert out["acq_date_kyiv"].to_list() == [kyiv_day]


def test_labels_and_types() -> None:
    """
    Labels and types.
    """
    out = parse_bronze(bronze({}, nrt(confidence="h", daynight="D")))
    assert out["satellite"].cast(pl.String).to_list() == ["noaa20", "noaa20"]
    assert out["product"].cast(pl.String).to_list() == ["sp", "nrt"]
    assert out["collection"].to_list() == [2, 2]
    assert out["confidence"].cast(pl.String).to_list() == ["nominal", "high"]
    assert out["daynight"].cast(pl.String).to_list() == ["night", "day"]
    assert out["type"].to_list() == [0, None]
    assert out["frp"].dtype == pl.Float32
    assert out["pixel_area_km2"].to_list() == pytest.approx([0.2, 0.2])
    assert out["acq_date"].to_list() == [date(2025, 7, 15)] * 2


@pytest.mark.parametrize(
    "row",
    [
        {"version": "3"},
        {"confidence": "x"},
        {"daynight": "X"},
        {"source": "MODIS_SP"},
        {"type": "9"},
        {"frp": "abc"},
        {"latitude": ""},
        {"acq_time": "12a"},
        {"acq_time": "2460"},
        {"version": "2.0NRT"},  # NRT version on an SP source
    ],
)
def test_bad_values_fail_instead_of_becoming_null(row: dict[str, object]) -> None:
    """
    Bad values fail instead of becoming null.
    """
    with pytest.raises(DataError):
        parse_bronze(bronze(row))


def test_detection_id_is_stable_and_distinguishes_rows() -> None:
    """
    Detection id is stable and distinguishes rows.
    """
    first = parse_bronze(bronze({}, {"acq_time": "52"}, {"source": "VIIRS_NOAA20_NRT", "version": "2.0NRT", "type": None}))
    again = parse_bronze(bronze({"requested_at": datetime(2026, 11, 20, tzinfo=UTC)}))
    ids = first["detection_id"].to_list()
    assert len(set(ids)) == 3
    assert again["detection_id"].to_list() == ids[:1]
    assert all(len(i) == 32 for i in ids)


def test_empty_bronze_gives_empty_typed_frame() -> None:
    """
    Empty bronze gives empty typed frame.
    """
    assert parse_bronze(bronze()).height == 0
