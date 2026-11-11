"""
The Dagster code location: `dagster dev -m firms_ua.orchestration.definitions`.
"""

from typing import Final

import dagster as dg

from firms_ua.orchestration.assets import firms_bronze, firms_raw
from firms_ua.orchestration.resources import FirmsPipeline
from firms_ua.orchestration.schedules import forward_fill_schedule, ingest_job

defs: Final = dg.Definitions(
    assets=[firms_raw, firms_bronze],
    jobs=[ingest_job],
    schedules=[forward_fill_schedule],
    resources={"pipeline": FirmsPipeline()},
)
