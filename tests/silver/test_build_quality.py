"""
One silver day end to end (pure), its reconciliation and the quality checks.
"""

from datetime import UTC, date, datetime

import polars as pl
import pytest

from bronze_factory import bronze, nrt
from firms_ua.common.sources import default_catalog
from firms_ua.datacatalog.silver import FirmsSilver, H3DailyActivity
from firms_ua.silver import quality
from firms_ua.silver.border import default_border
from firms_ua.silver.build import DayCounts, finish_day, prepare_day

DAY = date(2025, 7, 15)
NO_ACTIVITY = pl.DataFrame(schema=H3DailyActivity.polars_schema())


def day_bronze() -> pl.DataFrame:
    """
    Return one bronze day with a repeat, a superseded response, rows outside and inside the buffer, and NRT.
    """
    return bronze(
        {"latitude": "50.1"},
        {"latitude": "50.1"},  # exact repeat
        {
            "latitude": "50.2",
            "requested_at": datetime(2026, 1, 1, tzinfo=UTC),
        },  # an older response of the same source and day: superseded by the others
        {"latitude": "53.90", "longitude": "27.56"},  # Minsk: outside the buffer
        {"latitude": "48.37", "longitude": "27.70"},  # Moldova, inside the buffer
        nrt(latitude="50.3"),
    )


def test_prepare_counts_reconcile() -> None:
    """
    Prepare counts reconcile.
    """
    rows, counts = prepare_day(day_bronze(), default_border(), 30.0)
    assert counts == DayCounts(bronze_rows=6, superseded=1, duplicates=1, outside_buffer=1, kept=3)
    assert counts.reconciles()
    assert rows.filter(pl.col("product") == "nrt")["is_preferred"].to_list() == [False]


def test_finish_day_matches_schema_and_is_deterministic() -> None:
    """
    Finish day matches schema and is deterministic.
    """
    rows, counts = prepare_day(day_bronze(), default_border(), 30.0)
    out = finish_day(DAY, rows, rows.clear(), NO_ACTIVITY, "run-1")
    FirmsSilver.check(out)
    again = finish_day(DAY, rows.reverse(), rows.clear(), NO_ACTIVITY, "run-1")
    assert out.equals(again)
    assert quality.reconciliation(counts, out.height) == []
    assert out["in_ukraine"].to_list().count(False) == 1


def test_finish_day_uses_previous_day_tail_for_pass_ids() -> None:
    """
    Finish day uses previous day tail for pass ids.
    """
    border = default_border()
    previous, _ = prepare_day(bronze({"acq_date": "2025-07-14", "acq_time": "2358"}), border, 30.0)
    rows, _ = prepare_day(bronze({"acq_time": "3"}), border, 30.0)
    out = finish_day(DAY, rows, previous, NO_ACTIVITY, "run-1")
    assert out["pass_id"].to_list() == ["noaa20_20250714T2358"]


def test_empty_day() -> None:
    """
    Empty day.
    """
    rows, counts = prepare_day(bronze(), default_border(), 30.0)
    out = finish_day(DAY, rows, rows, NO_ACTIVITY, "run-1")
    FirmsSilver.check(out)
    assert counts == DayCounts(bronze_rows=0, superseded=0, duplicates=0, outside_buffer=0, kept=0)


def silver_day(*rows: dict[str, object]) -> pl.DataFrame:
    """
    Build the silver frame of DAY from bronze rows.
    """
    prepared, _ = prepare_day(bronze(*rows), default_border(), 30.0)
    return finish_day(DAY, prepared, prepared.clear(), NO_ACTIVITY, "run-1")


def test_value_ranges() -> None:
    """
    Value ranges.
    """
    assert quality.value_ranges(silver_day({})) == []
    problems = quality.value_ranges(silver_day({"frp": "-1"}, {"latitude": "50.2", "scan": "1.5"}))
    assert [p.split(":")[0] for p in problems] == ["frp", "scan"]


def test_partition_and_ids() -> None:
    """
    Partition and ids.
    """
    df = silver_day({}, {"latitude": "50.2"})
    assert quality.in_partition(df, DAY) == []
    assert quality.in_partition(df, date(2025, 7, 16)) != []
    assert quality.unique_ids(df) == []
    assert quality.unique_ids(pl.concat([df, df])) != []
    assert quality.keys_not_null(df) == []


@pytest.mark.parametrize(("noaa21_rows", "expected"), [(0, ["noaa21: 0 rows"]), (1, [])])
def test_satellite_gap(noaa21_rows: int, expected: list[str]) -> None:
    """
    Satellite gap.
    """
    many: list[dict[str, object]] = [{"latitude": f"50.{i:03d}"} for i in range(quality.GAP_MIN_OTHER_ROWS)]
    other: list[dict[str, object]] = [{"source": "VIIRS_NOAA21_SP", "latitude": "49.5"}] * noaa21_rows
    df = silver_day(*many, *other)
    # S-NPP has no rows either; it is covered on this day, so it is reported too.
    assert [p for p in quality.satellite_gaps(df, DAY, default_catalog()) if "noaa21" in p] == expected


def test_preferred_jump() -> None:
    """
    Preferred jump.
    """
    assert quality.preferred_jump(None, 1.0) == []
    assert quality.preferred_jump(1.0, 0.9) == []
    assert quality.preferred_jump(1.0, 0.2) != []
