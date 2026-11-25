"""
Jobs, schedules and sensors: the ingestion runs on its own, with no manual launch.

- `ingest_schedule` (daily, on by default) requests every raw partition Dagster has not materialized yet. The first tick
  is the historical backfill (one run per satellite over 2022-02-24 .. yesterday); later ticks fetch the new day and
  retry any day whose run failed.
- Bronze follows raw through declarative automation: `ingestion_automation` builds bronze for every raw partition that
  was just materialized.
- Silver follows bronze the same way (`silver_automation`). Its history is built once by a manual backfill of
  `silver_job` (activity first, then silver; see `orchestration/README.md`).
"""

from datetime import timedelta
from typing import Final

import dagster as dg

from firms_ua.common.settings import Settings
from firms_ua.common.sources import PIPELINE_START, default_catalog
from firms_ua.orchestration.assets import firms_bronze, firms_raw
from firms_ua.orchestration.partitions import to_key, to_partitions
from firms_ua.orchestration.planning import missing_ranges
from firms_ua.orchestration.silver_assets import firms_h3_activity, firms_silver

# 06:00 UTC leaves several hours after the day's last overpass for NRT to arrive; detections that arrive later are filled
# in when SP replaces NRT.
INGEST_CRON: Final = "0 6 * * *"
_RANGE_START_TAG: Final = "dagster/asset_partition_range_start"
_RANGE_END_TAG: Final = "dagster/asset_partition_range_end"

ingest_job: Final = dg.define_asset_job(
    "firms_ingest_job",
    selection=[firms_raw],
    description="FIRMS API -> raw for the selected (day, satellite) partitions; bronze follows automatically.",
)

# Evaluates `firms_bronze`'s automation condition every minute and launches bronze runs (as backfills, so a whole
# backfill's partitions are built in one run). Running by default: without it bronze is never built.
ingestion_automation: Final = dg.AutomationConditionSensorDefinition(
    "ingestion_automation",
    target=dg.AssetSelection.assets(firms_bronze),
    default_status=dg.DefaultSensorStatus.RUNNING,
    minimum_interval_seconds=60,
)

silver_job: Final = dg.define_asset_job(
    "firms_silver_job",
    selection=[firms_h3_activity, firms_silver],
    description="Bronze -> silver (H3 activity, then detections) for the selected days; use it for the history backfill.",
)

# Rebuilds silver partitions whose bronze (or activity history) changed. Running by default.
silver_automation: Final = dg.AutomationConditionSensorDefinition(
    "silver_automation",
    target=dg.AssetSelection.assets(firms_h3_activity, firms_silver),
    default_status=dg.DefaultSensorStatus.RUNNING,
    minimum_interval_seconds=60,
)


@dg.schedule(job=ingest_job, cron_schedule=INGEST_CRON, execution_timezone="UTC", default_status=dg.DefaultScheduleStatus.RUNNING)
def ingest_schedule(context: dg.ScheduleEvaluationContext) -> list[dg.RunRequest]:
    """
    Request one run per satellite and range of consecutive days that are not materialized yet (up to yesterday).
    """
    today = context.scheduled_execution_time.date()
    materialized = set(to_partitions(context.instance.get_materialized_partitions(firms_raw.key)))
    catalog = default_catalog(Settings().snpp_last_day)
    ranges = missing_ranges(catalog, materialized, PIPELINE_START, today - timedelta(days=1))
    return [
        dg.RunRequest(
            run_key=f"ingest:{today.isoformat()}:{satellite}:{first.isoformat()}:{last.isoformat()}",
            tags={
                _RANGE_START_TAG: to_key((satellite, first)),
                _RANGE_END_TAG: to_key((satellite, last)),
                "trigger": "ingest_schedule",
            },
        )
        for satellite, first, last in ranges
    ]
