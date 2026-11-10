"""
Read and write the ingestion log (one small file per entry, in the raw storage).
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime

import polars as pl

from firms_ua.common.windows import Window
from firms_ua.datacatalog.ingestion_log import IngestionLog
from firms_ua.storage.base import Storage

# (source, start_date, day_range)
WindowKey = tuple[str, date, int]
# (source, start_date, day_range, requested_at in epoch microseconds)
RequestKey = tuple[str, date, int, int]


def epoch_us(moment: datetime) -> int:
    """
    Return `moment` as UTC epoch microseconds (used instead of tz-aware datetimes, which need a tz database on Windows).
    """
    return int(moment.timestamp() * 1_000_000)


@dataclass(frozen=True)
class LogEntry:
    """
    The outcome of one step for one request window.
    """

    window: Window
    stage: str
    status: str
    requested_at: datetime
    http_status: int | None = None
    rows: int | None = None
    size_bytes: int | None = None
    error: str | None = None


def request_key(window: Window, requested_at: datetime) -> RequestKey:
    """
    Identify one raw object: its window and request time.
    """
    return (window.source, window.start, window.day_range, epoch_us(requested_at))


def entry_frame(entry: LogEntry, logged_at: datetime) -> pl.DataFrame:
    """
    Build the one-row frame for an entry, in the table's column order.
    """
    utc = pl.Datetime("us", "UTC")
    row = pl.DataFrame(
        {
            "start_date": [entry.window.start],
            "day_range": [entry.window.day_range],
            "stage": [entry.stage],
            "status": [entry.status],
            "http_status": [entry.http_status],
            "rows": [entry.rows],
            "size_bytes": [entry.size_bytes],
            "requested_at": [entry.requested_at],
            "logged_at": [logged_at],
            "error": [entry.error],
            "source": [entry.window.source],
        },
        schema={
            "start_date": pl.Date,
            "day_range": pl.Int16,
            "stage": pl.String,
            "status": pl.String,
            "http_status": pl.Int16,
            "rows": pl.Int64,
            "size_bytes": pl.Int64,
            "requested_at": utc,
            "logged_at": utc,
            "error": pl.String,
            "source": pl.String,
        },
    )
    return row


def record(store: Storage, entry: LogEntry, logged_at: datetime | None = None) -> str:
    """
    Append one entry to the log and return the key written.
    """
    ts = logged_at or datetime.now(UTC)
    (key,) = IngestionLog.write(entry_frame(entry, ts), store, ts)
    return key


def read_log(store: Storage) -> pl.DataFrame:
    """
    Return the whole log (an empty frame with the right schema if nothing was logged yet).
    """
    if not IngestionLog.has_files(store):
        return pl.DataFrame(schema=IngestionLog.polars_schema())
    return IngestionLog.scan_dataset(store).collect()


def ok_windows(log: pl.DataFrame, stage: str) -> set[WindowKey]:
    """
    Windows that have at least one successful entry for `stage`.
    """
    ok = log.filter((pl.col("stage") == stage) & (pl.col("status") == "ok"))
    return set(zip(ok["source"].to_list(), ok["start_date"].to_list(), ok["day_range"].to_list(), strict=True))


def ok_requests(log: pl.DataFrame, stage: str) -> set[RequestKey]:
    """
    Raw objects (window plus request time) that have a successful entry for `stage`.
    """
    ok = log.filter((pl.col("stage") == stage) & (pl.col("status") == "ok"))
    return set(
        zip(
            ok["source"].to_list(),
            ok["start_date"].to_list(),
            ok["day_range"].to_list(),
            ok["requested_at"].dt.epoch("us").to_list(),
            strict=True,
        )
    )
