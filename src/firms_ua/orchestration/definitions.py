"""
The Dagster code location: `dagster dev -m firms_ua.orchestration.definitions`.
"""

from typing import Final

import dagster as dg

from firms_ua.orchestration.assets import firms_bronze, firms_raw
from firms_ua.orchestration.resources import FirmsPipeline
from firms_ua.orchestration.schedules import ingest_job, ingest_schedule, ingestion_automation

defs: Final = dg.Definitions(
    assets=[firms_raw, firms_bronze],
    jobs=[ingest_job],
    schedules=[ingest_schedule],
    sensors=[ingestion_automation],
    resources={"pipeline": FirmsPipeline()},
)
