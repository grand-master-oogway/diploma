"""
Tests for the satellite to source mapping and grid-aligned window planning.
"""

from datetime import date, timedelta

import pytest

from firms_ua.common.sources import (
    NRT_FIRST_DAY,
    PIPELINE_START,
    SP_LAST_DAY,
    Satellite,
    contiguous_runs,
    default_catalog,
    source_for,
    windows_for,
    windows_for_days,
)
from firms_ua.common.windows import Window

CATALOG = default_catalog()
NOAA20 = CATALOG["noaa20"]
NOAA21 = CATALOG["noaa21"]
SNPP = CATALOG["snpp"]


def _days(windows: list[Window]) -> list[date]:
    return [w.start + timedelta(days=i) for w in windows for i in range(w.day_range)]


@pytest.mark.parametrize(
    ("satellite", "day", "expected"),
    [
        (NOAA20, PIPELINE_START, "VIIRS_NOAA20_SP"),
        (NOAA20, SP_LAST_DAY, "VIIRS_NOAA20_SP"),
        (NOAA20, NRT_FIRST_DAY, "VIIRS_NOAA20_NRT"),
        (NOAA21, date(2023, 2, 28), None),
        (NOAA21, date(2023, 3, 1), "VIIRS_NOAA21_SP"),
        (SNPP, date(2026, 11, 2), "VIIRS_SNPP_NRT"),
        (SNPP, date(2026, 11, 3), None),
    ],
)
def test_source_for_boundaries(satellite: Satellite, day: date, expected: str | None) -> None:
    """
    SP serves up to its last day, NRT after it; days outside a satellite's life have no source.
    """
    assert source_for(satellite, day) == expected


def test_windows_cover_every_covered_day_once_and_split_at_sp_nrt() -> None:
    """
    The full history is covered without gaps or overlap, and no window mixes SP and NRT.
    """
    windows = windows_for(NOAA20, PIPELINE_START, date(2026, 11, 10), 5)
    days = _days(windows)
    assert days == [PIPELINE_START + timedelta(days=i) for i in range((date(2026, 11, 10) - PIPELINE_START).days + 1)]
    assert all(w.day_range <= 5 for w in windows)
    for w in windows:
        last = w.start + timedelta(days=w.day_range - 1)
        assert source_for(NOAA20, w.start) == source_for(NOAA20, last) == w.source


def test_windows_sit_on_a_fixed_grid_so_keys_are_stable() -> None:
    """
    Runs that start on different days produce the same window keys, so the ingestion log can skip them.
    """
    full = set(windows_for(NOAA20, PIPELINE_START, date(2024, 12, 31), 5))
    later = windows_for(NOAA20, date(2024, 1, 1), date(2024, 12, 31), 5)
    # Every window of a later-starting run except the clipped first one is a window of the full run.
    assert set(later[1:]) <= full


def test_noaa21_starts_at_first_sp_day_and_snpp_stops_at_its_last_day() -> None:
    """
    No request is planned before NOAA-21's first SP day or after S-NPP's last day.
    """
    assert windows_for(NOAA21, PIPELINE_START, date(2023, 3, 1), 5) == [Window("VIIRS_NOAA21_SP", date(2023, 3, 1), 1)]
    assert _days(windows_for(SNPP, date(2026, 10, 30), date(2026, 11, 10), 5))[-1] == date(2026, 11, 2)
    assert windows_for(SNPP, date(2026, 11, 3), date(2026, 11, 10), 5) == []


def test_windows_for_days_splits_gaps() -> None:
    """
    Non-consecutive days are planned as separate runs and no day in between is requested.
    """
    days = [date(2024, 3, 1), date(2024, 3, 2), date(2024, 3, 10)]
    assert contiguous_runs(days) == [(date(2024, 3, 1), date(2024, 3, 2)), (date(2024, 3, 10), date(2024, 3, 10))]
    assert _days(windows_for_days(NOAA20, days, 5)) == days


def test_rejects_non_positive_day_range() -> None:
    """
    A window size below one day is an error.
    """
    with pytest.raises(ValueError, match="max_day_range"):
        windows_for(NOAA20, PIPELINE_START, PIPELINE_START, 0)
