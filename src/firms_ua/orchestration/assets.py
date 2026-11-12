"""
Ingestion assets: FIRMS API -> raw (CSV) -> bronze (Parquet).

Both assets are thin wrappers around `firms_ua.ingestion.runner`. A run receives a set of `(day, satellite)`
partitions (a single-run backfill hands over the whole range at once). Each day is fetched once: days the ingestion log
already covers are left out before 5-day request windows are planned on a fixed grid, so bronze gets no duplicate
responses. The ingestion log, not Dagster's metadata, is the record of what was fetched and built.
"""

from collections import defaultdict
from datetime import date, timedelta
from typing import Final

import dagster as dg

from firms_ua.common.sources import default_catalog
from firms_ua.ingestion.log import DayKey, covered_days, read_log
from firms_ua.ingestion.runner import build_objects, fetch_windows
from firms_ua.orchestration.partitions import ingest_partitions, to_partitions
from firms_ua.orchestration.planning import Partition, expected_days, run_windows
from firms_ua.orchestration.resources import FirmsPipeline
from firms_ua.raw.store import RawObject, list_raw
from firms_ua.storage.base import Storage

# Concurrency pool for anything that spends the MAP_KEY budget; its limit (1) is set in dagster.yaml.
FIRMS_API_POOL: Final = "firms_api"
COMPLETE_CHECK: Final = "days_complete"
# Build bronze for a partition as soon as its raw partition is materialized (and nothing upstream is missing or running).
# `eager()` alone only looks at the latest day; history partitions must follow raw too, so that restriction is removed.
BRONZE_AUTOMATION: Final = dg.AutomationCondition.eager().without(dg.AutomationCondition.in_latest_time_window())
_GROUP: Final = "ingestion"
_MAX_LISTED: Final = 20


class RawConfig(dg.Config):
    """
    Run options for `firms_raw`.
    """

    # Fetch again even if the days are already in the ingestion log (manual repair only; it adds a second copy to bronze).
    force: bool = False


def _partitions(context: dg.AssetExecutionContext) -> list[Partition]:
    return to_partitions(context.partition_keys)


def _describe(days: list[DayKey]) -> str:
    shown = [f"{source} {day}" for source, day in days[:_MAX_LISTED]]
    more = len(days) - len(shown)
    return "; ".join(shown) + (f"; ... and {more} more" if more else "")


@dg.asset(
    partitions_def=ingest_partitions,
    backfill_policy=dg.BackfillPolicy.single_run(),
    pool=FIRMS_API_POOL,
    group_name=_GROUP,
    kinds={"python", "csv"},
    description="Unchanged FIRMS API responses (CSV) per request window, in the raw bucket.",
)
def firms_raw(context: dg.AssetExecutionContext, config: RawConfig, pipeline: FirmsPipeline) -> dg.MaterializeResult:
    """
    Fetch the run's days that are not fetched yet into raw; fail the run if any request failed.
    """
    settings = pipeline.settings()
    raw = pipeline.storage(settings, "raw")
    partitions = _partitions(context)
    catalog = default_catalog(settings.snpp_last_day)
    done = frozenset() if config.force else covered_days(read_log(raw), "raw")
    windows = run_windows(catalog, partitions, settings.max_day_range, done=done)
    expected = len(expected_days(catalog, partitions))
    context.log.info("%d partitions, %d source-days, %d request windows (force=%s)", len(partitions), expected, len(windows), config.force)
    report = fetch_windows(raw, windows, pipeline.fetcher(settings), force=config.force)
    metadata = {
        "partitions": len(partitions),
        "source_days": expected,
        "windows": len(windows),
        "fetched": report.done,
        "failed": report.failed,
    }
    if report.failed:
        raise dg.Failure(f"{report.failed} of {len(windows)} windows failed; see the ingestion log", metadata=metadata)
    return dg.MaterializeResult(metadata=metadata)


def _raw_objects(raw: Storage, days: list[DayKey], max_day_range: int) -> list[RawObject]:
    """
    List the raw objects whose window contains at least one of `days`.
    """
    by_source: defaultdict[str, set[date]] = defaultdict(set)
    for source, day in days:
        by_source[source].add(day)
    found: list[RawObject] = []
    for source, wanted in sorted(by_source.items()):
        # A window that holds the earliest wanted day may start up to `max_day_range - 1` days before it.
        objects = list_raw(raw, source, min(wanted) - timedelta(days=max_day_range - 1), max(wanted))
        found.extend(o for o in objects if any(o.window.start + timedelta(days=i) in wanted for i in range(o.window.day_range)))
    return found


@dg.asset(
    partitions_def=ingest_partitions,
    backfill_policy=dg.BackfillPolicy.single_run(),
    deps=[firms_raw],
    automation_condition=BRONZE_AUTOMATION,
    group_name=_GROUP,
    kinds={"python", "parquet"},
    check_specs=[dg.AssetCheckSpec(COMPLETE_CHECK, asset="firms_bronze", blocking=True)],
    description="FIRMS detections as Parquet, one file per source and acq_date, in the bronze bucket.",
)
def firms_bronze(context: dg.AssetExecutionContext, pipeline: FirmsPipeline) -> dg.MaterializeResult:
    """
    Build bronze from the raw objects of the run's days, then check every day is logged `ok` for raw and bronze.
    """
    settings = pipeline.settings()
    raw = pipeline.storage(settings, "raw")
    partitions = _partitions(context)
    days = expected_days(default_catalog(settings.snpp_last_day), partitions)
    report = build_objects(raw, pipeline.storage(settings, "bronze"), _raw_objects(raw, days, settings.max_day_range))
    log = read_log(raw)
    in_raw, in_bronze = covered_days(log, "raw"), covered_days(log, "bronze")
    no_raw = [d for d in days if d not in in_raw]
    no_bronze = [d for d in days if d not in in_bronze]
    check = dg.AssetCheckResult(
        check_name=COMPLETE_CHECK,
        passed=not no_raw and not no_bronze and report.failed == 0,
        metadata={
            "source_days": len(days),
            "missing_raw": len(no_raw),
            "missing_bronze": len(no_bronze),
            "build_failed": report.failed,
            "missing": _describe(no_raw + no_bronze),
        },
    )
    return dg.MaterializeResult(
        metadata={
            "partitions": len(partitions),
            "source_days": len(days),
            "built": report.done,
            "skipped": report.skipped,
            "failed": report.failed,
        },
        check_results=[check],
    )
