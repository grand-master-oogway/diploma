"""
Tests for window planning.
"""

from datetime import date

import pytest

from firms_ua.windows import plan_windows


def test_covers_every_day_once() -> None:
    """
    Windows tile the range without gaps or overlap.
    """
    ws = plan_windows("S", date(2024, 1, 1), date(2024, 1, 12), 5)
    assert [w.day_range for w in ws] == [5, 5, 2]
    assert ws[1].start == date(2024, 1, 6)


def test_single_day() -> None:
    """
    A one-day range yields one one-day window.
    """
    assert len(plan_windows("S", date(2024, 1, 1), date(2024, 1, 1), 5)) == 1


def test_invalid_range() -> None:
    """
    Non-positive max range is rejected.
    """
    with pytest.raises(ValueError, match="max_day_range"):
        plan_windows("S", date(2024, 1, 1), date(2024, 1, 2), 0)
