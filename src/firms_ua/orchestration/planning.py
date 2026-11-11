"""
Pure planning for the Dagster ingestion assets (no Dagster imports, no clock).

A partition is `(satellite, day)`. These functions turn the partitions of one run into the `(source, day)` pairs it
must deliver and the request windows still needed, and pick the partitions the forward-fill schedule looks at.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Set
from datetime import date, timedelta

from firms_ua.common.sources import Satellite, covers, source_for, windows_for_days
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


def forward_fill_partitions(catalog: Mapping[str, Satellite], today: date, lookback_days: int) -> list[Partition]:
    """
    Return the partitions of the last `lookback_days` complete UTC days before `today`, per covered satellite.

    Days already fetched are skipped by the asset, so in a normal day only yesterday is requested; the older days
    catch up a day missed because a run failed or the schedule was off.
    """
    days = [today - timedelta(days=offset) for offset in range(lookback_days, 0, -1)]
    return [(name, day) for name, satellite in sorted(catalog.items()) for day in days if covers(satellite, day)]
