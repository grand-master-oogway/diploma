"""
Tests for the ingestion log and the pipeline steps that write it (no network).
"""

from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest

from firms_ua.common.errors import FirmsError, SchemaError
from firms_ua.common.windows import Window
from firms_ua.datacatalog.ingestion_log import IngestionLog
from firms_ua.firms_api.models import FirmsResponse
from firms_ua.ingestion.log import LogEntry, ok_requests, ok_windows, read_log, record, request_key
from firms_ua.ingestion.runner import build_objects, fetch_windows
from firms_ua.raw.store import list_raw
from firms_ua.storage.base import Storage
from firms_ua.storage.local import LocalStorage

HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
ROW = "50.1,30.2,330.1,0.4,0.4,2024-03-01,0007,N20,VIIRS,n,2.0NRT,290.1,1.2,N\n"
W1 = Window("VIIRS_NOAA20_NRT", date(2024, 3, 1), 1)
W2 = Window("VIIRS_NOAA20_NRT", date(2024, 3, 2), 1)
T0 = datetime(2024, 3, 5, 10, tzinfo=UTC)


class Clock:
    """
    A clock that moves one second per call, so every request gets a distinct timestamp.
    """

    def __init__(self) -> None:
        """
        Start at T0.
        """
        self._now = T0

    def __call__(self) -> datetime:
        """
        Return the current fake time and advance it.
        """
        self._now += timedelta(seconds=1)
        return self._now


def ok_response(rows: int = 1) -> FirmsResponse:
    """
    A valid response with `rows` data rows.
    """
    return FirmsResponse((HEADER + ROW * rows).encode(), 200, "https://example/***", rows)


def test_empty_log_has_the_right_schema(store: Storage) -> None:
    """
    Before anything is logged, reading gives an empty frame with the declared columns.

    (Reading logged data goes through Polars, which cannot use the in-memory GCS fake, so those tests use local storage.)
    """
    log = read_log(store)
    assert log.height == 0
    assert log.schema == IngestionLog.polars_schema()


def test_record_roundtrip_and_ok_sets(local_store: LocalStorage) -> None:
    """
    Entries are stored one file each; only `ok` entries count as done, per stage.
    """
    record(local_store, LogEntry(W1, "raw", "ok", T0, http_status=200, rows=3, size_bytes=99), T0)
    record(local_store, LogEntry(W2, "raw", "failed", T0, http_status=429, error="HTTP 429"), T0 + timedelta(seconds=1))
    record(local_store, LogEntry(W1, "bronze", "ok", T0, rows=3), T0 + timedelta(seconds=2))
    log = read_log(local_store)
    IngestionLog.check(log)
    assert log.height == 3
    assert len(local_store.list_keys("ingestion_log/")) == 3
    assert ok_windows(log, "raw") == {(W1.source, W1.start, 1)}
    assert ok_windows(log, "bronze") == {(W1.source, W1.start, 1)}
    assert ok_requests(log, "bronze") == {request_key(W1, T0)}
    assert ok_requests(log, "raw") == {request_key(W1, T0)}
    failed = log.filter(pl.col("status") == "failed")
    assert failed["http_status"].to_list() == [429]
    assert failed["error"].to_list() == ["HTTP 429"]


def test_invalid_stage_is_rejected(store: Storage) -> None:
    """
    The table definition guards the allowed values.
    """
    with pytest.raises(SchemaError):
        record(store, LogEntry(W1, "nonsense", "ok", T0), T0)
    assert store.list_keys("") == []


def test_fetch_logs_skips_and_continues_after_failure(local_store: LocalStorage) -> None:
    """
    A failed window is logged and does not stop the run; finished windows are skipped on rerun; force refetches.
    """
    calls: list[Window] = []

    def fetcher(window: Window) -> FirmsResponse:
        calls.append(window)
        if window == W2:
            raise FirmsError("HTTP 503 for https://example/***", http_status=503)
        return ok_response(rows=2)

    clock = Clock()
    report = fetch_windows(local_store, [W1, W2], fetcher, now=clock)
    assert (report.done, report.skipped, report.failed) == (1, 0, 1)
    log = read_log(local_store)
    assert sorted(zip(log["start_date"].to_list(), log["stage"].to_list(), log["status"].to_list(), strict=True)) == [
        (W1.start, "raw", "ok"),
        (W2.start, "raw", "failed"),
    ]
    assert log.filter(pl.col("status") == "failed")["http_status"].to_list() == [503]
    assert len(list_raw(local_store, W1.source, date(2024, 1, 1), date(2024, 12, 31))) == 1  # only W1 reached raw

    calls.clear()
    again = fetch_windows(local_store, [W1, W2], fetcher, now=clock)  # W1 is skipped, the failed W2 is retried
    assert calls == [W2]
    assert (again.done, again.skipped, again.failed) == (0, 1, 1)

    calls.clear()
    forced = fetch_windows(local_store, [W1], fetcher, force=True, now=clock)
    assert calls == [W1]
    assert forced.done == 1
    assert len(list_raw(local_store, W1.source, date(2024, 1, 1), date(2024, 12, 31))) == 2  # new object, nothing overwritten


def test_build_logs_rows_and_never_rebuilds(tmp_path) -> None:
    """
    Bronze builds are logged; an empty response is logged ok with rows=0 and is not built again.
    """
    raw, bronze = LocalStorage(tmp_path / "raw"), LocalStorage(tmp_path / "bronze")
    bodies = {W1: HEADER + ROW * 2, W2: HEADER}
    fetch_windows(
        raw,
        [W1, W2],
        lambda w: FirmsResponse(bodies[w].encode(), 200, "u", len(bodies[w].splitlines()) - 1),
        now=Clock(),
    )
    objects = list_raw(raw, W1.source, date(2024, 1, 1), date(2024, 12, 31))

    report = build_objects(raw, bronze, objects)
    assert (report.done, report.skipped, report.failed) == (2, 0, 0)
    log = read_log(raw).filter(pl.col("stage") == "bronze").sort("start_date")
    assert log["rows"].to_list() == [2, 0]
    assert len(bronze.list_keys("firms_viirs/")) == 1  # the empty response wrote no file

    again = build_objects(raw, bronze, objects)
    assert (again.done, again.skipped, again.failed) == (0, 2, 0)


def test_build_failure_is_logged_and_run_continues(tmp_path) -> None:
    """
    A response with an unexpected column fails its build, is logged, and does not block the next object.
    """
    raw, bronze = LocalStorage(tmp_path / "raw"), LocalStorage(tmp_path / "bronze")
    bad = HEADER.replace("daynight", "daynight,surprise") + ROW.rstrip("\n") + ",x\n"
    bodies = {W1: bad, W2: HEADER + ROW}
    fetch_windows(raw, [W1, W2], lambda w: FirmsResponse(bodies[w].encode(), 200, "u", 1), now=Clock())
    objects = list_raw(raw, W1.source, date(2024, 1, 1), date(2024, 12, 31))
    report = build_objects(raw, bronze, objects)
    assert (report.done, report.failed) == (1, 1)
    failed = read_log(raw).filter((pl.col("stage") == "bronze") & (pl.col("status") == "failed"))
    assert failed["start_date"].to_list() == [W1.start]
    assert "surprise" in failed["error"][0]
