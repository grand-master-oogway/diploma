"""
Tests for the raw layer (run against every storage backend).
"""

from datetime import UTC, date, datetime

import pytest

from firms_ua.common.windows import Window
from firms_ua.raw.store import list_raw, read_raw, write_raw
from firms_ua.storage.base import Storage

W = Window("VIIRS_NOAA20_NRT", date(2024, 3, 1), 1)
T1 = datetime(2024, 3, 2, 10, 0, 0, 123456, tzinfo=UTC)
T2 = datetime(2024, 3, 2, 11, tzinfo=UTC)


def test_bytes_stored_unchanged_with_layout(store: Storage) -> None:
    """
    Bytes are stored exactly as given, under the documented key.
    """
    content = b"latitude,longitude\r\n50.1,30.2\r\n"
    obj = write_raw(store, W, content, T1)
    assert read_raw(store, obj) == content
    assert obj.key == "firms/source=VIIRS_NOAA20_NRT/start_date=2024-03-01/day_range=1/requested_at=20240302T100000123456Z.csv"


def test_never_overwrites(store: Storage) -> None:
    """
    The same window and timestamp cannot be written twice; a later timestamp adds an object.
    """
    write_raw(store, W, b"a", T1)
    with pytest.raises(FileExistsError):
        write_raw(store, W, b"b", T1)
    write_raw(store, W, b"c", T2)
    assert len(store.list_keys("firms/")) == 2


def test_list_raw_filters_and_parses(store: Storage) -> None:
    """
    Listing parses window and request time from the key, filters by start date, and sorts.
    """
    write_raw(store, Window(W.source, date(2024, 3, 3), 2), b"x", T2)
    write_raw(store, W, b"y", T1)
    write_raw(store, Window(W.source, date(2024, 4, 1), 1), b"z", T1)
    found = list_raw(store, W.source, date(2024, 3, 1), date(2024, 3, 31))
    assert [(o.window.start, o.window.day_range, o.requested_at) for o in found] == [
        (date(2024, 3, 1), 1, T1),
        (date(2024, 3, 3), 2, T2),
    ]
    assert list_raw(store, "OTHER", date(2024, 1, 1), date(2024, 12, 31)) == []
