"""
Partitions of the ingestion assets: one UTC day x one satellite.
"""

from collections.abc import Iterable
from datetime import date
from typing import Final

import dagster as dg

from firms_ua.common.sources import PIPELINE_START, default_catalog
from firms_ua.orchestration.planning import Partition

DATE_DIM: Final = "date"
SATELLITE_DIM: Final = "satellite"

ingest_partitions: Final = dg.MultiPartitionsDefinition(
    {
        DATE_DIM: dg.DailyPartitionsDefinition(start_date=PIPELINE_START.isoformat(), timezone="UTC"),
        SATELLITE_DIM: dg.StaticPartitionsDefinition(sorted(default_catalog())),
    }
)


def to_partition(key: str) -> Partition:
    """
    Parse a multi-partition key (`"2024-03-01|noaa20"`) into `(satellite, day)`.
    """
    dims = ingest_partitions.get_partition_key_from_str(key).keys_by_dimension
    return dims[SATELLITE_DIM], date.fromisoformat(dims[DATE_DIM])


def to_partitions(keys: Iterable[str]) -> list[Partition]:
    """
    Parse several multi-partition keys.
    """
    return [to_partition(k) for k in keys]


def to_key(partition: Partition) -> dg.MultiPartitionKey:
    """
    Build the multi-partition key of `(satellite, day)`.
    """
    satellite, day = partition
    return dg.MultiPartitionKey({DATE_DIM: day.isoformat(), SATELLITE_DIM: satellite})
