"""
Overpass ids and the persistent-hotspot window.
"""

from datetime import UTC, date, datetime, timedelta

import polars as pl

from firms_ua.silver.hotspots import daily_activity, flag_hotspots, persistent_cells
from firms_ua.silver.passes import assign_passes


def detections(*items: tuple[str, datetime]) -> pl.DataFrame:
    """
    Return (satellite, acq_time) rows.
    """
    return pl.DataFrame(
        {"satellite": [s for s, _ in items], "acq_time": [t for _, t in items]},
        schema={"satellite": pl.String, "acq_time": pl.Datetime("us", "UTC")},
    )


def at(hour: int, minute: int, day: int = 15) -> datetime:
    """
    Return a UTC time on July `day`, 2025.
    """
    return datetime(2025, 7, day, hour, minute, tzinfo=UTC)


def test_gap_over_20_minutes_starts_a_new_pass_per_satellite() -> None:
    """
    Gap over 20 minutes starts a new pass per satellite.
    """
    df = detections(("noaa20", at(1, 0)), ("noaa21", at(1, 5)), ("noaa20", at(1, 19)), ("noaa20", at(1, 45)), ("noaa20", at(1, 10)))
    assert assign_passes(df)["pass_id"].to_list() == [
        "noaa20_20250715T0100",
        "noaa21_20250715T0105",
        "noaa20_20250715T0100",
        "noaa20_20250715T0145",
        "noaa20_20250715T0100",
    ]


def test_pass_crossing_midnight_keeps_its_start_id() -> None:
    """
    Pass crossing midnight keeps its start id.
    """
    df = detections(("noaa20", at(23, 58, day=14)), ("noaa20", at(0, 3)))
    assert assign_passes(df)["pass_id"].to_list() == ["noaa20_20250714T2358"] * 2


def activity(cell_days: dict[int, list[date]]) -> pl.DataFrame:
    """
    Return activity rows from cell -> active days.
    """
    rows = [(cell, d) for cell, days in cell_days.items() for d in days]
    return pl.DataFrame(
        {"h3_r9": [c for c, _ in rows], "detections": [1] * len(rows), "acq_date": [d for _, d in rows]},
        schema={"h3_r9": pl.UInt64, "detections": pl.UInt32, "acq_date": pl.Date},
    )


def test_hotspot_window_uses_only_past_days() -> None:
    """
    Hotspot window uses only past days.
    """
    day = date(2025, 7, 15)
    past = [day - timedelta(days=i) for i in range(1, 31)]  # 30 past days
    act = activity({1: past, 2: past[:29] + [day], 3: [*past[:29], day - timedelta(days=366)]})
    assert persistent_cells(act, day).to_list() == [1]


def test_flag_and_daily_activity() -> None:
    """
    Flag and daily activity.
    """
    df = pl.DataFrame(
        {"h3_r9": [1, 1, 2, 3], "is_preferred": [True, True, True, False], "acq_date": [date(2025, 7, 15)] * 4},
        schema={"h3_r9": pl.UInt64, "is_preferred": pl.Boolean, "acq_date": pl.Date},
    )
    assert daily_activity(df).rows() == [(1, 2, date(2025, 7, 15)), (2, 1, date(2025, 7, 15))]
    cells = pl.Series([2], dtype=pl.UInt64)
    assert flag_hotspots(df, cells)["is_persistent_hotspot"].to_list() == [False, False, True, False]
