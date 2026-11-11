"""
Jobs and schedules: the forward fill (each new day fetched once). Backfills are launched from the UI.
"""

from typing import Final

import dagster as dg

from firms_ua.common.settings import Settings
from firms_ua.common.sources import default_catalog
from firms_ua.orchestration.assets import firms_bronze, firms_raw
from firms_ua.orchestration.partitions import to_key
from firms_ua.orchestration.planning import forward_fill_partitions

# Look at the last few complete UTC days; days already fetched are skipped, so normally only yesterday is requested and
# the older ones only catch up after a failed run or a pause. Fetching at 06:00 UTC leaves several hours after the day's
# last overpass for NRT to arrive; detections that arrive later are filled in when SP replaces NRT.
LOOKBACK_DAYS: Final = 3

ingest_job: Final = dg.define_asset_job(
    "firms_ingest_job",
    selection=[firms_raw, firms_bronze],
    description="FIRMS API -> raw -> bronze for the selected (day, satellite) partitions.",
)


@dg.schedule(job=ingest_job, cron_schedule="0 6 * * *", execution_timezone="UTC", default_status=dg.DefaultScheduleStatus.STOPPED)
def forward_fill_schedule(context: dg.ScheduleEvaluationContext) -> list[dg.RunRequest]:
    """
    Request the last `LOOKBACK_DAYS` days for every satellite still delivering, one run per partition (no refetch).
    """
    today = context.scheduled_execution_time.date()
    catalog = default_catalog(Settings().snpp_last_day)
    return [
        dg.RunRequest(
            run_key=f"forward-fill:{today.isoformat()}:{satellite}:{day.isoformat()}",
            partition_key=to_key((satellite, day)),
            tags={"trigger": "forward_fill"},
        )
        for satellite, day in forward_fill_partitions(catalog, today, LOOKBACK_DAYS)
    ]
