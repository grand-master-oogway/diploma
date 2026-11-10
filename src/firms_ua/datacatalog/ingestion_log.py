"""
Ingestion log table (lives in the raw layer).
"""

import pandera.polars as pa
import polars as pl

from firms_ua.datacatalog_core.parquet_table import ParquetTable


class IngestionLog(ParquetTable):
    """
    One row per attempt of a pipeline step for a request window.

    It is the only record that tells a quiet day (`ok`, zero rows) from a missing day (no row at all) from a failure
    (`failed`), and it lets reruns skip finished windows. Rows are only ever added.
    """

    start_date: pl.Date = pa.Field(description="First day of the request window")
    day_range: pl.Int16 = pa.Field(description="Number of days in the request window")
    stage: pl.String = pa.Field(isin=["raw", "bronze"], description="Step that was run")
    status: pl.String = pa.Field(isin=["ok", "failed"], description="Outcome")
    http_status: pl.Int16 = pa.Field(nullable=True, description="HTTP status of the FIRMS response, if one was received")
    rows: pl.Int64 = pa.Field(nullable=True, description="Data rows in the response (raw) or written to bronze")
    size_bytes: pl.Int64 = pa.Field(nullable=True, description="Size of the raw response in bytes")
    requested_at: pl.Datetime(time_unit="us", time_zone="UTC") = pa.Field(
        description="When the FIRMS request was made (identifies the raw object; bronze rows reuse it)"
    )
    logged_at: pl.Datetime(time_unit="us", time_zone="UTC") = pa.Field(description="When this row was written")
    error: pl.String = pa.Field(nullable=True, description="Failure message (never contains the MAP_KEY)")
    source: pl.String = pa.Field(description="FIRMS source id (partition)")

    class Config:
        """
        Table identity and layout.
        """

        name = "raw.ingestion_log"
        metadata = {"version": 1, "partition_by": ("source",)}
