"""
Persistent hotspots: H3 r9 cells with detections on many past days (industrial flares, plants, landfills).

This replaces SP's `type` = 2 ("other static land source"), which NRT lacks, with one rule for both products. The flag of
day D uses only days D-`WINDOW_DAYS` .. D-1, so a model trained on it never sees the future.
"""

from datetime import date, timedelta
from typing import Final

import polars as pl

WINDOW_DAYS: Final = 365
# Provisional: a cell active on at least this many of the past 365 days. Set from the distribution in
# docs/silver_findings.md after profiling bronze.
MIN_ACTIVE_DAYS: Final = 30


def daily_activity(df: pl.DataFrame) -> pl.DataFrame:
    """
    Count preferred detections per `h3_r9` cell and UTC day: columns `h3_r9`, `detections`, `acq_date`.
    """
    return (
        df.filter(pl.col("is_preferred"))
        .group_by("h3_r9", "acq_date")
        .agg(pl.len().cast(pl.UInt32).alias("detections"))
        .select("h3_r9", "detections", "acq_date")
        .sort("acq_date", "h3_r9")
    )


def window(day: date) -> tuple[date, date]:
    """
    Return the inclusive range of past days that decides `day`'s flag.
    """
    return day - timedelta(days=WINDOW_DAYS), day - timedelta(days=1)


def persistent_cells(activity: pl.DataFrame, day: date, min_active_days: int = MIN_ACTIVE_DAYS) -> pl.Series:
    """
    Return the `h3_r9` cells active on at least `min_active_days` distinct days in `window(day)`.

    In the first year of the series the window is partly empty, so fewer cells qualify; that is a known limitation.
    """
    first, last = window(day)
    return (
        activity.filter(pl.col("acq_date").is_between(first, last))
        .group_by("h3_r9")
        .agg(pl.col("acq_date").n_unique().alias("days"))
        .filter(pl.col("days") >= min_active_days)["h3_r9"]
    )


def flag_hotspots(df: pl.DataFrame, cells: pl.Series) -> pl.DataFrame:
    """
    Add `is_persistent_hotspot`: the detection's `h3_r9` cell is in `cells`.
    """
    return df.with_columns(pl.col("h3_r9").is_in(cells.implode()).alias("is_persistent_hotspot"))
