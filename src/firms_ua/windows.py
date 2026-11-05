"""Pure request-window planning."""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Window:
    """One API request: `day_range` days starting at `start`."""

    source: str
    start: date
    day_range: int


def plan_windows(source: str, start: date, end: date, max_day_range: int) -> list[Window]:
    """Split `[start, end]` (inclusive) into windows of at most `max_day_range` days.

    Args:
        source: FIRMS source id, e.g. `VIIRS_NOAA20_NRT`.
        start: First day, inclusive.
        end: Last day, inclusive.
        max_day_range: Maximum days per request.

    Returns:
        Ordered, non-overlapping windows covering every day exactly once.
    """
    if max_day_range < 1:
        msg = "max_day_range must be >= 1"
        raise ValueError(msg)
    windows: list[Window] = []
    cur = start
    while cur <= end:
        n = min(max_day_range, (end - cur).days + 1)
        windows.append(Window(source, cur, n))
        cur += timedelta(days=n)
    return windows
