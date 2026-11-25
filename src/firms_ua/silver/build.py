"""
The silver transform of one UTC day, as pure functions over in-memory frames.

`prepare_day` turns one day of bronze into typed, located, deduplicated rows (shared by both silver tables);
`finish_day` adds what needs other days (passes, persistent hotspots) and the run id, in the table's column order.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time

import polars as pl

from firms_ua.datacatalog.silver import FirmsSilver
from firms_ua.silver.border import Border, locate
from firms_ua.silver.cells import add_cells
from firms_ua.silver.hotspots import flag_hotspots, persistent_cells
from firms_ua.silver.parse import parse_bronze
from firms_ua.silver.passes import PASS_LOOKBACK, assign_passes
from firms_ua.silver.resolve import drop_repeats, latest_responses, mark_preferred


@dataclass(frozen=True, slots=True, kw_only=True)
class DayCounts:
    """
    Where one day's bronze rows went: `bronze_rows` = `superseded` + `duplicates` + `outside_buffer` + `kept`.
    """

    bronze_rows: int
    superseded: int
    duplicates: int
    outside_buffer: int
    kept: int

    def reconciles(self) -> bool:
        """
        True if every bronze row is accounted for.
        """
        return self.bronze_rows == self.superseded + self.duplicates + self.outside_buffer + self.kept


def prepare_day(bronze: pl.DataFrame, border: Border, buffer_km: float) -> tuple[pl.DataFrame, DayCounts]:
    """
    Type one UTC day of bronze (all sources) and keep the rows silver stores.

    Steps: latest response per source, typing, exact-repeat removal, H3 cells, border location, the buffer cut,
    and the SP-over-NRT preference.

    Raises:
        DataError: If a bronze value does not parse or a label is unknown.
    """
    latest = latest_responses(bronze)
    typed, duplicates = drop_repeats(parse_bronze(latest))
    located = locate(add_cells(typed), border)
    kept = mark_preferred(located.filter(pl.col("border_distance_km") <= buffer_km))
    counts = DayCounts(
        bronze_rows=bronze.height,
        superseded=bronze.height - latest.height,
        duplicates=duplicates,
        outside_buffer=located.height - kept.height,
        kept=kept.height,
    )
    return kept, counts


def finish_day(day: date, rows: pl.DataFrame, previous: pl.DataFrame, activity: pl.DataFrame, run_id: str) -> pl.DataFrame:
    """
    Build the silver frame of `day` from its prepared rows.

    Args:
        day: The UTC day.
        rows: `prepare_day` output for `day`.
        previous: `prepare_day` output for the day before (may be empty); only its last `PASS_LOOKBACK` is used, so a
            pass crossing midnight keeps one id.
        activity: `H3DailyActivity` rows covering at least the hotspot window of `day`.
        run_id: Id of the run that builds the partition.

    Returns:
        A frame in `FirmsSilver` column order, sorted by time, satellite and id (identical for identical input).
    """
    midnight = datetime.combine(day, time(), tzinfo=UTC)
    tail = previous.filter(pl.col("acq_time") >= midnight - PASS_LOOKBACK)
    with_passes = assign_passes(pl.concat([tail, rows], how="vertical")).filter(pl.col("acq_date") == day)
    flagged = flag_hotspots(with_passes, persistent_cells(activity, day))
    return (
        flagged.with_columns(pl.lit(run_id, dtype=pl.String).alias("run_id"))
        .select(FirmsSilver.column_names())
        .sort("acq_time", "satellite", "detection_id")
    )
