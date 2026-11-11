"""
Tests for the pure planning behind the Dagster assets and the forward-fill schedule.
"""

from datetime import date

from firms_ua.common.sources import default_catalog
from firms_ua.common.windows import Window
from firms_ua.orchestration.partitions import to_key, to_partition
from firms_ua.orchestration.planning import days_by_satellite, expected_days, forward_fill_partitions, run_windows

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


def test_forward_fill_skips_satellites_past_their_last_day() -> None:
    """
    The forward fill covers the last complete days only, and not S-NPP after its delivery ended.
    """
    parts = forward_fill_partitions(CATALOG, date(2026, 11, 11), 3)
    assert ("noaa20", date(2026, 11, 8)) in parts
    assert ("noaa21", date(2026, 11, 10)) in parts
    assert not any(name == "snpp" for name, _ in parts)
    assert not any(day == date(2026, 11, 11) for _, day in parts)
    assert len(parts) == 6
