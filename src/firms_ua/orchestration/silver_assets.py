"""
Silver assets: bronze -> `silver.h3_r9_daily_activity` and `silver.firms_detections`, one UTC day per partition.

Both act as the `silver` service account when `FIRMS_SILVER_SERVICE_ACCOUNT` is set (the Dagster VM's own account
cannot read bronze or delete in silver). Each partition is replaced as a whole, so reruns are safe. A run with many
partitions (a single-run backfill) works through them in chunks of `CHUNK_DAYS` to bound memory.

The activity table is built from bronze, not from silver, so the hotspot flag of day D (which needs days D-365..D-1)
creates no cycle. Changing an old day re-triggers the silver days whose window contains it: the price of the flag.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from itertools import batched
from typing import Final

import dagster as dg
import polars as pl

from firms_ua.common.sources import default_catalog
from firms_ua.datacatalog.bronze import FirmsBronze
from firms_ua.datacatalog.silver import FirmsSilver, H3DailyActivity
from firms_ua.datacatalog_core.parquet_table import ParquetTable
from firms_ua.orchestration.assets import firms_bronze
from firms_ua.orchestration.partitions import DATE_DIM, silver_partitions
from firms_ua.orchestration.resources import FirmsPipeline
from firms_ua.silver import quality
from firms_ua.silver.border import default_border
from firms_ua.silver.build import DayCounts, finish_day, prepare_day
from firms_ua.silver.hotspots import WINDOW_DAYS, daily_activity
from firms_ua.storage.base import Storage

CHUNK_DAYS: Final = 31
# Rebuild a partition whenever an upstream partition it reads changes (including late satellites and SP replacing
# NRT). Unlike `eager()`, missing upstream partitions do not block: (day, satellite) partitions a satellite does not
# cover are never materialized. History is built by a manual backfill, not by this condition.
SILVER_AUTOMATION: Final = (
    dg.AutomationCondition.any_deps_updated().since_last_handled()
    & ~dg.AutomationCondition.any_deps_in_progress()
    & ~dg.AutomationCondition.in_progress()
).with_label("rebuild_when_upstream_changes")
_GROUP: Final = "silver"
_BRONZE_BY_DAY: Final = dg.AssetDep(
    firms_bronze, partition_mapping=dg.MultiToSingleDimensionPartitionMapping(partition_dimension_name=DATE_DIM)
)
_MAX_LISTED: Final = 20

# Blocking checks stop the run (nothing of a failing day is written); warnings are reported only.
BLOCKING_CHECKS: Final = ("keys_not_null", "unique_ids", "in_partition", "value_ranges", "reconciliation")
WARNING_CHECKS: Final = ("satellite_gaps", "preferred_jump")


def _days(context: dg.AssetExecutionContext) -> list[date]:
    return sorted(date.fromisoformat(k) for k in context.partition_keys)


def _read_days(table: type[ParquetTable], store: Storage, first: date, last: date) -> pl.DataFrame:
    """
    Read a table's partitions with `acq_date` in `[first, last]`; an empty frame if the table has no files yet.
    """
    try:
        lf = table.scan_dataset(store)
    except FileNotFoundError:
        return pl.DataFrame(schema=table.polars_schema())
    day = pl.col("acq_date")
    if table.polars_schema()["acq_date"] == pl.String:  # bronze keeps the partition value as text
        day = day.str.to_date("%Y-%m-%d")
    return lf.filter(day.is_between(first, last)).collect()


def _bronze_day(bronze: pl.DataFrame, day: date) -> pl.DataFrame:
    return bronze.filter(pl.col("acq_date") == day.isoformat())


def _chunks(days: Sequence[date]) -> Iterable[tuple[date, ...]]:
    return batched(days, CHUNK_DAYS, strict=False)


def _describe(problems: dict[date, list[str]]) -> str:
    items = sorted(problems.items())
    shown = [f"{day}: {'; '.join(p)}" for day, p in items[:_MAX_LISTED]]
    more = len(items) - len(shown)
    return " | ".join(shown) + (f" | ... and {more} more days" if more else "")


def _check_result(name: str, problems: dict[date, list[str]], *, blocking: bool) -> dg.AssetCheckResult:
    return dg.AssetCheckResult(
        check_name=name,
        passed=not problems,
        severity=dg.AssetCheckSeverity.ERROR if blocking else dg.AssetCheckSeverity.WARN,
        metadata={"failed_days": len(problems), "details": _describe(problems)},
    )


def _storages(pipeline: FirmsPipeline) -> tuple[Storage, Storage, float]:
    settings = pipeline.settings()
    acting_as = settings.silver_service_account
    bronze = pipeline.storage(settings, "bronze", impersonate=acting_as)
    silver = pipeline.storage(settings, "silver", impersonate=acting_as)
    return bronze, silver, settings.border_buffer_km


@dg.asset(
    partitions_def=silver_partitions,
    backfill_policy=dg.BackfillPolicy.single_run(),
    deps=[_BRONZE_BY_DAY],
    automation_condition=SILVER_AUTOMATION,
    group_name=_GROUP,
    kinds={"python", "parquet"},
    description="Preferred detections per H3 r9 cell and UTC day, from bronze; input of the persistent-hotspot flag.",
)
def firms_h3_activity(context: dg.AssetExecutionContext, pipeline: FirmsPipeline) -> dg.MaterializeResult:
    """
    Replace the activity partition of every day in the run.
    """
    bronze_store, silver_store, buffer_km = _storages(pipeline)
    border = default_border()
    written_at = datetime.now(UTC)
    days = _days(context)
    rows = cells = 0
    for chunk in _chunks(days):
        bronze = _read_days(FirmsBronze, bronze_store, chunk[0], chunk[-1])
        for day in chunk:
            prepared, _ = prepare_day(_bronze_day(bronze, day), border, buffer_km)
            activity = daily_activity(prepared)
            H3DailyActivity.replace_partition(activity, silver_store, written_at, {"acq_date": day})
            rows += prepared.height
            cells += activity.height
    return dg.MaterializeResult(metadata={"days": len(days), "detections": rows, "cell_days": cells})


@dg.asset(
    partitions_def=silver_partitions,
    backfill_policy=dg.BackfillPolicy.single_run(),
    deps=[
        _BRONZE_BY_DAY,
        dg.AssetDep(
            firms_h3_activity,
            partition_mapping=dg.TimeWindowPartitionMapping(
                start_offset=-WINDOW_DAYS, end_offset=-1, allow_nonexistent_upstream_partitions=True
            ),
        ),
    ],
    automation_condition=SILVER_AUTOMATION,
    group_name=_GROUP,
    kinds={"python", "parquet"},
    check_specs=[dg.AssetCheckSpec(name, asset="firms_silver", blocking=True) for name in BLOCKING_CHECKS]
    + [dg.AssetCheckSpec(name, asset="firms_silver", blocking=False) for name in WARNING_CHECKS],
    description="Typed FIRMS detections with H3 cells, passes, border and quality flags, one partition per UTC day.",
)
def firms_silver(context: dg.AssetExecutionContext, pipeline: FirmsPipeline) -> dg.MaterializeResult:
    """
    Build, check and replace the silver partition of every day in the run.

    A day that fails a blocking check is not written (its previous version stays); the run then fails after the other
    days are written, so no partition of the run is recorded as materialized with bad data.
    """
    bronze_store, silver_store, buffer_km = _storages(pipeline)
    border = default_border()
    catalog = default_catalog(pipeline.settings().snpp_last_day)
    written_at = datetime.now(UTC)
    days = _days(context)
    activity = _read_days(H3DailyActivity, silver_store, days[0] - timedelta(days=WINDOW_DAYS), days[-1] - timedelta(days=1))
    problems: dict[str, dict[date, list[str]]] = {name: {} for name in (*BLOCKING_CHECKS, *WARNING_CHECKS)}
    totals: defaultdict[str, int] = defaultdict(int)
    previous_share: float | None = None
    for chunk in _chunks(days):
        bronze = _read_days(FirmsBronze, bronze_store, chunk[0] - timedelta(days=1), chunk[-1])
        before, _ = prepare_day(_bronze_day(bronze, chunk[0] - timedelta(days=1)), border, buffer_km)
        for day in chunk:
            rows, counts = prepare_day(_bronze_day(bronze, day), border, buffer_km)
            frame = finish_day(day, rows, before, activity, context.run.run_id)
            before = rows
            share = quality.preferred_share(frame)
            found = {
                "keys_not_null": quality.keys_not_null(frame),
                "unique_ids": quality.unique_ids(frame),
                "in_partition": quality.in_partition(frame, day),
                "value_ranges": quality.value_ranges(frame),
                "reconciliation": quality.reconciliation(counts, frame.height),
                "satellite_gaps": quality.satellite_gaps(frame, day, catalog),
                "preferred_jump": quality.preferred_jump(previous_share, share),
            }
            previous_share = share
            for name, issues in found.items():
                if issues:
                    problems[name][day] = issues
            if any(found[name] for name in BLOCKING_CHECKS):
                continue
            FirmsSilver.replace_partition(
                frame,
                silver_store,
                written_at,
                {"acq_date": day},
                file_metadata={"boundary": border.name, "boundary_sha256": border.sha256, "run_id": context.run.run_id},
            )
            _add_totals(totals, counts, frame)
    checks = [_check_result(n, problems[n], blocking=True) for n in BLOCKING_CHECKS]
    checks += [_check_result(n, problems[n], blocking=False) for n in WARNING_CHECKS]
    failed = sorted({day for name in BLOCKING_CHECKS for day in problems[name]})
    if failed:
        details = {name: _describe(problems[name]) for name in BLOCKING_CHECKS if problems[name]}
        msg = f"{len(failed)} of {len(days)} days failed blocking checks and were not written: {failed[:_MAX_LISTED]}"
        raise dg.Failure(msg, metadata=details)
    return dg.MaterializeResult(metadata={"days": len(days), **totals, "boundary_sha256": border.sha256}, check_results=checks)


def _add_totals(totals: defaultdict[str, int], counts: DayCounts, frame: pl.DataFrame) -> None:
    totals["rows"] += frame.height
    totals["bronze_rows"] += counts.bronze_rows
    totals["dropped_superseded"] += counts.superseded
    totals["dropped_duplicates"] += counts.duplicates
    totals["dropped_outside_buffer"] += counts.outside_buffer
    totals["rows_in_ukraine"] += int(frame["in_ukraine"].sum())
    totals["rows_preferred"] += int(frame["is_preferred"].sum())
    totals["rows_invalid_brightness"] += int(frame["flag_invalid_brightness"].sum())
    totals["rows_persistent_hotspot"] += int(frame["is_persistent_hotspot"].sum())
    for product, n in frame.group_by(pl.col("product").cast(pl.String)).len().iter_rows():
        totals[f"rows_{product}"] += n
    for satellite, n in frame.group_by(pl.col("satellite").cast(pl.String)).len().iter_rows():
        totals[f"rows_{satellite}"] += n
