"""
Run the pipeline steps over many windows, recording every outcome in the ingestion log.

These functions hold the orchestration logic (skip finished work, log successes and failures, keep going after a failure)
so that the CLI and later Dagster assets only call them.
"""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

import polars as pl

from firms_ua.bronze.builder import build_bronze
from firms_ua.common.errors import FirmsError, SchemaError
from firms_ua.common.windows import Window
from firms_ua.firms_api.models import FirmsResponse
from firms_ua.ingestion.log import LogEntry, ok_requests, ok_windows, read_log, record, request_key
from firms_ua.raw.store import RawObject, write_raw
from firms_ua.storage.base import Storage

log = logging.getLogger(__name__)

_MAX_ERROR_CHARS = 500


@dataclass(frozen=True)
class StepReport:
    """
    Counts for one run of a step.
    """

    done: int = 0
    skipped: int = 0
    failed: int = 0


def _short(error: Exception) -> str:
    return str(error)[:_MAX_ERROR_CHARS]


def fetch_windows(
    raw: Storage,
    windows: Iterable[Window],
    fetcher: Callable[[Window], FirmsResponse],
    *,
    force: bool = False,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> StepReport:
    """
    Fetch each window into raw and log it; windows with a successful `raw` entry are skipped unless `force`.

    A failed window is logged as `failed` and the run continues with the next one. The order per window is: raw object
    first, then the log row, so a crash in between leaves the window to be fetched again, never half-recorded.
    """
    finished = ok_windows(read_log(raw), "raw")
    done = skipped = failed = 0
    for window in windows:
        key = (window.source, window.start, window.day_range)
        if not force and key in finished:
            log.info("skip %s %s (+%d days): already fetched", window.source, window.start, window.day_range)
            skipped += 1
            continue
        requested_at = now()
        log.info("fetch %s %s (+%d days)", window.source, window.start, window.day_range)
        try:
            resp = fetcher(window)
        except FirmsError as e:
            record(raw, LogEntry(window, "raw", "failed", requested_at, http_status=e.http_status, error=_short(e)))
            log.error("fetch failed for %s %s: %s", window.source, window.start, _short(e))
            failed += 1
            continue
        obj = write_raw(raw, window, resp.content, requested_at)
        record(
            raw,
            LogEntry(window, "raw", "ok", requested_at, http_status=resp.status, rows=resp.row_count, size_bytes=len(resp.content)),
        )
        finished.add(key)
        log.info("raw written: %s rows=%d", obj.key, resp.row_count)
        done += 1
    return StepReport(done, skipped, failed)


def build_objects(raw: Storage, bronze: Storage, objects: Iterable[RawObject]) -> StepReport:
    """
    Build bronze from each raw object and log it; objects with a successful `bronze` entry are skipped.

    A response with zero rows writes no bronze file but is logged `ok` with `rows=0`, so it is not rebuilt. A failing
    object is logged `failed` and the run continues.
    """
    built = ok_requests(read_log(raw), "bronze")
    done = skipped = failed = 0
    for obj in objects:
        key = request_key(obj.window, obj.requested_at)
        if key in built:
            skipped += 1
            continue
        try:
            result = build_bronze(raw, bronze, obj)
        except (SchemaError, pl.exceptions.PolarsError) as e:
            record(raw, LogEntry(obj.window, "bronze", "failed", obj.requested_at, error=_short(e)))
            log.error("bronze build failed for %s: %s", obj.key, _short(e))
            failed += 1
            continue
        record(raw, LogEntry(obj.window, "bronze", "ok", obj.requested_at, rows=result.rows))
        built.add(key)
        done += 1
    return StepReport(done, skipped, failed)
