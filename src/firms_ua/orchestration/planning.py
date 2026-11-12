"""
Pure planning for the Dagster ingestion assets (no Dagster imports, no clock).

A partition is `(satellite, day)`. These functions turn the partitions of one run into the `(source, day)` pairs it
must deliver and the request windows still needed, and find the ranges the automatic ingestion schedule requests.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Set
from datetime import date, timedelta

from firms_ua.common.sources import Satellite, contiguous_runs, covers, source_for, windows_for_days
from firms_ua.common.windows import Window
from firms_ua.ingestion.log import DayKey

type Partition = tuple[str, date]


def days_by_satellite(partitions: Iterable[Partition]) -> dict[str, list[date]]:
    """
    Group partition days by satellite name, each list sorted.
    """
    grouped: defaultdict[str, set[date]] = defaultdict(set)
    for satellite, day in partitions:
        grouped[satellite].add(day)
    return {name: sorted(days) for name, days in grouped.items()}


def expected_days(catalog: Mapping[str, Satellite], partitions: Iterable[Partition]) -> list[DayKey]:
    """
    Return the `(source, day)` pairs the partitions must deliver; days a satellite does not cover are left out.

    Raises:
        KeyError: If a partition names a satellite missing from `catalog`.
    """
    found: list[DayKey] = []
    for name, days in sorted(days_by_satellite(partitions).items()):
        for day in days:
            source = source_for(catalog[name], day)
            if source is not None:
                found.append((source, day))
    return found


def run_windows(
    catalog: Mapping[str, Satellite],
    partitions: Iterable[Partition],
    max_day_range: int,
    *,
    done: Set[DayKey] = frozenset(),
) -> list[Window]:
    """
    Plan the request windows for the partitions' days that are not in `done` (already fetched).

    Raises:
        KeyError: If a partition names a satellite missing from `catalog`.
    """
    windows: list[Window] = []
    for name, days in sorted(days_by_satellite(partitions).items()):
        satellite = catalog[name]
        todo = [d for d in days if (source := source_for(satellite, d)) is not None and (source, d) not in done]
        windows.extend(windows_for_days(satellite, todo, max_day_range))
    return windows


def missing_ranges(
    catalog: Mapping[str, Satellite],
    materialized: Set[Partition],
    first: date,
    last: date,
) -> list[tuple[str, date, date]]:
    """
    Return `(satellite, first_day, last_day)` runs of consecutive days in `[first, last]` that need fetching.

    A day needs fetching if the satellite covers it and its partition is not in `materialized`. On the first call this is
    the whole history (one range per satellite); afterwards normally just the newest day, plus any day whose run failed.
    """
    ranges: list[tuple[str, date, date]] = []
    for name, satellite in sorted(catalog.items()):
        days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
        todo = [d for d in days if covers(satellite, d) and (name, d) not in materialized]
        ranges.extend((name, a, b) for a, b in contiguous_runs(todo))
    return ranges
