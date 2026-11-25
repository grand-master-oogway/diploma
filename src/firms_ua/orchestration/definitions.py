"""
The Dagster code location: `dagster dev -m firms_ua.orchestration.definitions`.
"""

from typing import Final

import dagster as dg

from firms_ua.orchestration.assets import firms_bronze, firms_raw
from firms_ua.orchestration.resources import FirmsPipeline
from firms_ua.orchestration.schedules import ingest_job, ingest_schedule, ingestion_automation, silver_automation, silver_job
from firms_ua.orchestration.silver_assets import firms_h3_activity, firms_silver

defs: Final = dg.Definitions(
    assets=[firms_raw, firms_bronze, firms_h3_activity, firms_silver],
    jobs=[ingest_job, silver_job],
    schedules=[ingest_schedule],
    sensors=[ingestion_automation, silver_automation],
    resources={"pipeline": FirmsPipeline()},
)
