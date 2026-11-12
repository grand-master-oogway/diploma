"""
Tests for the pure planning behind the Dagster assets and the forward-fill schedule.
"""

from datetime import date, timedelta

from firms_ua.common.sources import default_catalog
from firms_ua.common.windows import Window
from firms_ua.orchestration.partitions import to_key, to_partition
from firms_ua.orchestration.planning import days_by_satellite, expected_days, missing_ranges, run_windows

CATALOG = default_catalog()


def test_partition_key_roundtrip() -> None:
    """
    A partition survives conversion to a Dagster key and back.
    """
    assert to_partition(to_key(("noaa21", date(2024, 3, 1)))) == ("noaa21", date(2024, 3, 1))


def test_days_by_satellite_groups_and_sorts() -> None:
    """
    Partitions are grouped per satellite with sorted days.
    """
    parts = [("snpp", date(2024, 3, 2)), ("snpp", date(2024, 3, 1)), ("noaa20", date(2024, 3, 1))]
    assert days_by_satellite(parts) == {"snpp": [date(2024, 3, 1), date(2024, 3, 2)], "noaa20": [date(2024, 3, 1)]}


def test_uncovered_partitions_plan_no_windows() -> None:
    """
    A partition outside the satellite's coverage plans no request.
    """
    assert run_windows(CATALOG, [("noaa21", date(2022, 6, 1))], 5) == []


def test_run_windows_per_satellite() -> None:
    """
    Each satellite's days map to its own source.
    """
    windows = run_windows(CATALOG, [("noaa20", date(2026, 8, 1)), ("snpp", date(2026, 8, 1))], 5)
    assert windows == [Window("VIIRS_NOAA20_NRT", date(2026, 8, 1), 1), Window("VIIRS_SNPP_NRT", date(2026, 8, 1), 1)]


def test_done_days_are_not_planned_and_expected_days_ignore_them() -> None:
    """
    Already fetched days get no window, but still count as days the run must deliver.
    """
    parts = [("noaa20", date(2026, 8, 1)), ("noaa20", date(2026, 8, 2)), ("noaa21", date(2022, 6, 1))]
    done = {("VIIRS_NOAA20_NRT", date(2026, 8, 1))}
    assert run_windows(CATALOG, parts, 5, done=done) == [Window("VIIRS_NOAA20_NRT", date(2026, 8, 2), 1)]
    assert expected_days(CATALOG, parts) == [("VIIRS_NOAA20_NRT", date(2026, 8, 1)), ("VIIRS_NOAA20_NRT", date(2026, 8, 2))]


def test_missing_ranges_first_run_is_the_whole_covered_history() -> None:
    """
    With nothing materialized, each satellite gets one range over the days it covers.
    """
    ranges = missing_ranges(CATALOG, set(), date(2022, 2, 24), date(2026, 11, 10))
    assert ranges == [
        ("noaa20", date(2022, 2, 24), date(2026, 11, 10)),
        ("noaa21", date(2023, 3, 1), date(2026, 11, 10)),
        ("snpp", date(2022, 2, 24), date(2026, 11, 2)),
    ]


def test_missing_ranges_later_runs_request_only_gaps_and_the_new_day() -> None:
    """
    Materialized days are left out; a failed day in the middle comes back as its own range.
    """
    last = date(2024, 3, 10)
    done = {("noaa20", date(2024, 3, 1) + timedelta(days=i)) for i in range(9)} - {("noaa20", date(2024, 3, 5))}
    ranges = missing_ranges({"noaa20": CATALOG["noaa20"]}, done, date(2024, 3, 1), last)
    assert ranges == [("noaa20", date(2024, 3, 5), date(2024, 3, 5)), ("noaa20", last, last)]
