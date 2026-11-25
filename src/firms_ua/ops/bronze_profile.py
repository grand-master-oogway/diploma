"""
Profile bronze before trusting silver's assumptions: labels, overpass hours, value ranges, recurring cells.

The numbers set the label tables (`silver/labels.py`), the value-range checks (`silver/quality.py`) and the
persistent-hotspot threshold (`silver/hotspots.py`), and back the Kyiv-day choice (no overpasses near Kyiv midnight).
"""

from typing import Any, Final

import polars as pl

from firms_ua.silver.cells import add_cells

QUANTILES: Final = (0.0, 0.001, 0.01, 0.5, 0.99, 0.999, 1.0)
MEASURES: Final = ("scan", "track", "bright_ti4", "bright_ti5", "frp")
ACTIVE_DAY_THRESHOLDS: Final = (5, 10, 20, 30, 50, 100, 200)


def versions(bronze: pl.LazyFrame) -> list[dict[str, Any]]:
    """
    Every `version` per source with its first and last day and row count.
    """
    return (
        bronze.group_by("source", "version")
        .agg(pl.col("acq_date").min().alias("first"), pl.col("acq_date").max().alias("last"), pl.len().alias("rows"))
        .sort("source", "version")
        .collect()
        .to_dicts()
    )


def hours(bronze: pl.LazyFrame) -> dict[str, list[int]]:
    """
    Rows per UTC hour of `acq_time` (index = hour), per source.
    """
    counts = (
        bronze.with_columns((pl.col("acq_time").cast(pl.Int32, strict=True) // 100).alias("hour"))
        .group_by("source", "hour")
        .len()
        .collect()
    )
    out: dict[str, list[int]] = {}
    for source, hour, n in counts.sort("source", "hour").iter_rows():
        out.setdefault(source, [0] * 24)[hour] = n
    return out


def value_quantiles(bronze: pl.LazyFrame) -> dict[str, dict[str, float]]:
    """
    Quantiles of the measurements (`QUANTILES`) over all rows.
    """
    numbers = bronze.select(pl.col(c).cast(pl.Float64, strict=True) for c in MEASURES).collect()
    return {c: {str(q): float(numbers[c].quantile(q) or 0.0) for q in QUANTILES} for c in MEASURES}


def active_days(bronze: pl.LazyFrame) -> dict[str, dict[str, int]]:
    """
    Per year: how many H3 r9 cells had a detection on at least N distinct days, for each N in `ACTIVE_DAY_THRESHOLDS`.
    """
    points = bronze.select(
        pl.col("latitude").cast(pl.Float64, strict=True),
        pl.col("longitude").cast(pl.Float64, strict=True),
        pl.col("acq_date"),
    ).collect()
    per_cell = (
        add_cells(points)
        .group_by(pl.col("acq_date").str.slice(0, 4).alias("year"), "h3_r9")
        .agg(pl.col("acq_date").n_unique().alias("days"))
    )
    return {
        year: {f">={n}": int((group["days"] >= n).sum()) for n in ACTIVE_DAY_THRESHOLDS} | {"cells": group.height}
        for (year,), group in sorted(per_cell.partition_by("year", as_dict=True).items())
    }


def profile(bronze: pl.LazyFrame) -> dict[str, Any]:
    """
    Run every profile over a bronze scan (string columns, `acq_date` as text).
    """
    return {
        "versions": versions(bronze),
        "utc_hours": hours(bronze),
        "value_quantiles": value_quantiles(bronze),
        "h3_r9_active_days": active_days(bronze),
    }
