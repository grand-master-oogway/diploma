"""
Satellite to FIRMS source mapping: which product (SP or NRT) serves which day.

FIRMS answers HTTP 200 with a header only for days a source does not cover, so the ranges are enforced here, in pure
code, and never discovered by requesting. The bounds come from `docs/probe_findings.md`; re-run `firms-ua probe` to
check them before a large backfill.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

from firms_ua.common.windows import Window

# First day of the project (and anchor of the request-window grid).
PIPELINE_START: Final = date(2022, 2, 24)
# Last day served by Standard Processing; Near Real-Time takes over the next day.
SP_LAST_DAY: Final = date(2026, 7, 31)
NRT_FIRST_DAY: Final = SP_LAST_DAY + timedelta(days=1)
# Suomi NPP delivery ceased on this day (default; overridable through settings).
SNPP_DEFAULT_LAST_DAY: Final = date(2026, 11, 2)


@dataclass(frozen=True, slots=True, kw_only=True)
class Satellite:
    """
    One VIIRS satellite and the days its SP and NRT sources cover.
    """

    name: str
    sp_source: str
    nrt_source: str
    first_day: date
    last_day: date | None = None


def default_catalog(snpp_last_day: date = SNPP_DEFAULT_LAST_DAY) -> dict[str, Satellite]:
    """
    Return the supported satellites by name.

    Args:
        snpp_last_day: Last day Suomi NPP delivers data (it is set in configuration, not hardcoded in callers).

    Returns:
        Mapping of satellite name to its definition. NOAA-21 starts with its first SP day; earlier days have no data.
    """
    satellites = (
        Satellite(name="noaa20", sp_source="VIIRS_NOAA20_SP", nrt_source="VIIRS_NOAA20_NRT", first_day=PIPELINE_START),
        Satellite(name="noaa21", sp_source="VIIRS_NOAA21_SP", nrt_source="VIIRS_NOAA21_NRT", first_day=date(2023, 3, 1)),
        Satellite(
            name="snpp",
            sp_source="VIIRS_SNPP_SP",
            nrt_source="VIIRS_SNPP_NRT",
            first_day=PIPELINE_START,
            last_day=snpp_last_day,
        ),
    )
    return {s.name: s for s in satellites}


def covers(satellite: Satellite, day: date) -> bool:
    """
    Tell whether the satellite has any source for `day`.
    """
    return day >= satellite.first_day and (satellite.last_day is None or day <= satellite.last_day)


def source_for(satellite: Satellite, day: date) -> str | None:
    """
    Return the FIRMS source id that serves `day`, or `None` when the satellite has no data that day.
    """
    if not covers(satellite, day):
        return None
    return satellite.sp_source if day <= SP_LAST_DAY else satellite.nrt_source


def _next_grid_start(day: date, step: int) -> date:
    """
    Return the first grid boundary after `day`; the grid starts at `PIPELINE_START` and repeats every `step` days.
    """
    offset = (day - PIPELINE_START).days
    return PIPELINE_START + timedelta(days=(offset // step + 1) * step)


def windows_for(satellite: Satellite, start: date, end: date, max_day_range: int) -> list[Window]:
    """
    Plan request windows for `[start, end]` (inclusive) with the right source for each day.

    Windows never cross the SP/NRT boundary, never include days the satellite does not cover, and sit on a fixed
    `max_day_range`-day grid anchored at `PIPELINE_START`. The grid keeps window keys stable between runs, so the
    ingestion log can recognise windows that were already fetched.

    Args:
        satellite: The satellite to plan for.
        start: First day, inclusive.
        end: Last day, inclusive.
        max_day_range: Maximum days per request.

    Returns:
        Ordered, non-overlapping windows; empty if the range holds no covered day.
    """
    if max_day_range < 1:
        msg = "max_day_range must be >= 1"
        raise ValueError(msg)
    windows: list[Window] = []
    cur = max(start, satellite.first_day)
    last = end if satellite.last_day is None else min(end, satellite.last_day)
    while cur <= last:
        source = source_for(satellite, cur)
        if source is None:
            break
        boundary = _next_grid_start(cur, max_day_range)
        if source == satellite.sp_source:
            boundary = min(boundary, NRT_FIRST_DAY)
        stop = min(boundary - timedelta(days=1), last)
        windows.append(Window(source, cur, (stop - cur).days + 1))
        cur = stop + timedelta(days=1)
    return windows


def contiguous_runs(days: Iterable[date]) -> list[tuple[date, date]]:
    """
    Group days into inclusive `(first, last)` runs of consecutive days, in order; duplicates are ignored.
    """
    runs: list[tuple[date, date]] = []
    for day in sorted(set(days)):
        if runs and day == runs[-1][1] + timedelta(days=1):
            runs[-1] = (runs[-1][0], day)
        else:
            runs.append((day, day))
    return runs


def windows_for_days(satellite: Satellite, days: Iterable[date], max_day_range: int) -> list[Window]:
    """
    Plan request windows for any set of days (for example the partitions of one Dagster run).
    """
    return [w for first, last in contiguous_runs(days) for w in windows_for(satellite, first, last, max_day_range)]


def satellite_of(catalog: Mapping[str, Satellite], source: str) -> Satellite | None:
    """
    Return the satellite that owns a FIRMS source id, or `None` if it is unknown.
    """
    for satellite in catalog.values():
        if source in (satellite.sp_source, satellite.nrt_source):
            return satellite
    return None
