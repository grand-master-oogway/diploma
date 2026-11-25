"""
Data-quality checks of a built silver day. Each returns a list of problems; an empty list means the check passed.
"""

from collections.abc import Mapping
from datetime import date
from types import MappingProxyType
from typing import Final

import polars as pl

from firms_ua.common.sources import Satellite, covers
from firms_ua.silver.build import DayCounts

KEY_COLUMNS: Final = ("detection_id", "acq_time", "latitude", "longitude", "satellite", "product")
# Inclusive plausible ranges (None: unbounded), checked against the 2022-02-24..2026-11-24 bronze profile
# (docs/silver_findings.json): scan 0.32-0.80, track 0.36-0.78, ti5 224.9-385.5, frp from 0. Brightness ranges apply only
# to rows without `flag_invalid_brightness` (ti4 = 0 occurs as a FIRMS fill value; otherwise ti4 >= 295 K).
VALUE_RANGES: Final[Mapping[str, tuple[float | None, float | None]]] = MappingProxyType(
    {
        "frp": (0.0, None),
        "scan": (0.25, 1.0),
        "track": (0.25, 1.0),
        "bright_ti4": (200.0, 400.0),
        "bright_ti5": (150.0, 400.0),
    }
)
BRIGHTNESS: Final = frozenset({"bright_ti4", "bright_ti5"})
# A satellite with no rows is suspicious only if another satellite saw at least this many that day.
GAP_MIN_OTHER_ROWS: Final = 50
# Warn when the preferred share moves more than this between consecutive days.
PREFERRED_SHARE_JUMP: Final = 0.5


def keys_not_null(df: pl.DataFrame) -> list[str]:
    """
    Key columns must have no nulls.
    """
    return [f"{c}: {n} nulls" for c in KEY_COLUMNS if (n := df[c].null_count())]


def unique_ids(df: pl.DataFrame) -> list[str]:
    """
    `detection_id` must not repeat within a source.
    """
    repeats = df.group_by("source", "detection_id").len().filter(pl.col("len") > 1)
    return [f"{repeats.height} repeated detection_id values"] if repeats.height else []


def in_partition(df: pl.DataFrame, day: date) -> list[str]:
    """
    Every `acq_time` must fall on the partition's UTC day.
    """
    outside = df.filter(pl.col("acq_time").dt.date() != day).height
    return [f"{outside} rows outside {day}"] if outside else []


def value_ranges(df: pl.DataFrame) -> list[str]:
    """
    Measurements must lie in `VALUE_RANGES`; brightness is not checked on rows flagged `flag_invalid_brightness`.
    """
    problems = []
    for column, (low, high) in VALUE_RANGES.items():
        bad = pl.lit(value=False)
        if low is not None:
            bad = bad | (pl.col(column) < low)
        if high is not None:
            bad = bad | (pl.col(column) > high)
        if column in BRIGHTNESS:
            bad = bad & ~pl.col("flag_invalid_brightness")
        if n := df.filter(bad).height:
            problems.append(f"{column}: {n} rows outside [{low}, {high}]")
    return problems


def reconciliation(counts: DayCounts, silver_rows: int) -> list[str]:
    """
    Every bronze row must be kept or counted as dropped, and the kept rows must be the rows written.
    """
    problems = []
    if not counts.reconciles():
        problems.append(f"bronze rows do not add up: {counts}")
    if counts.kept != silver_rows:
        problems.append(f"{counts.kept} rows kept but {silver_rows} rows in silver")
    return problems


def satellite_gaps(df: pl.DataFrame, day: date, catalog: Mapping[str, Satellite]) -> list[str]:
    """
    Name covered satellites with no rows on a day when another satellite has many (a possible outage or lost response).
    """
    rows = dict(df.group_by(pl.col("satellite").cast(pl.String)).len().iter_rows())
    if max(rows.values(), default=0) < GAP_MIN_OTHER_ROWS:
        return []
    return [f"{name}: 0 rows" for name, sat in sorted(catalog.items()) if covers(sat, day) and not rows.get(name)]


def preferred_share(df: pl.DataFrame) -> float | None:
    """
    Return the share of `is_preferred` rows, or None for an empty day.
    """
    return float(df["is_preferred"].mean()) if df.height else None  # type: ignore[arg-type]


def preferred_jump(previous: float | None, current: float | None) -> list[str]:
    """
    Flag a sharp change of the preferred share between consecutive days.
    """
    if previous is None or current is None or abs(current - previous) <= PREFERRED_SHARE_JUMP:
        return []
    return [f"preferred share moved from {previous:.2f} to {current:.2f}"]
