"""
Raw layer: the unchanged API response (CSV bytes), one object per request, never overwritten.

Key layout inside the raw storage:
`firms/source=<S>/start_date=<D>/day_range=<N>/requested_at=<UTC>.csv`.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

from firms_ua.storage import Storage
from firms_ua.windows import Window

_TS_FORMAT = "%Y%m%dT%H%M%S%fZ"
_KEY = re.compile(
    r"firms/source=(?P<source>[^/]+)/start_date=(?P<start>\d{4}-\d{2}-\d{2})/day_range=(?P<days>\d+)"
    r"/requested_at=(?P<ts>\d{8}T\d{12}Z)\.csv"
)


@dataclass(frozen=True)
class RawObject:
    """
    One stored response: the request window, when it was made, and where it lives.
    """

    window: Window
    requested_at: datetime
    key: str


def _window_prefix(window: Window) -> str:
    return f"firms/source={window.source}/start_date={window.start:%Y-%m-%d}/day_range={window.day_range}/"


def is_fetched(store: Storage, window: Window) -> bool:
    """
    True if raw already holds a response for this window.
    """
    return bool(store.list_keys(_window_prefix(window)))


def write_raw(store: Storage, window: Window, content: bytes, requested_at: datetime | None = None) -> RawObject:
    """
    Store the response bytes unchanged and return the new object.

    Raises:
        FileExistsError: If an object with the same window and timestamp exists (raw is never overwritten).
    """
    ts = requested_at or datetime.now(UTC)
    key = f"{_window_prefix(window)}requested_at={ts:{_TS_FORMAT}}.csv"
    store.put_new(key, content)
    return RawObject(window, ts, key)


def read_raw(store: Storage, obj: RawObject) -> bytes:
    """
    Return the stored bytes.
    """
    return store.get(obj.key)


def list_raw(store: Storage, source: str, start: date, end: date) -> list[RawObject]:
    """
    Return raw objects of `source` whose window starts in `[start, end]`, ordered by window start then request time.
    """
    found: list[RawObject] = []
    for key in store.list_keys(f"firms/source={source}/"):
        match = _KEY.fullmatch(key)
        if match is None:
            continue
        window = Window(source, date.fromisoformat(match["start"]), int(match["days"]))
        if start <= window.start <= end:
            found.append(RawObject(window, datetime.strptime(match["ts"], _TS_FORMAT).replace(tzinfo=UTC), key))
    return sorted(found, key=lambda o: (o.window.start, o.window.day_range, o.requested_at))
