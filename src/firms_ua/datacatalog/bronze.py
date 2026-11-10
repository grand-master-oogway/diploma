"""
Bronze tables.
"""

import pandera.polars as pa
import polars as pl

from firms_ua.datacatalog_core.parquet_table import ParquetTable


class FirmsBronze(ParquetTable):
    """
    Raw FIRMS VIIRS detections: every API column as a string, then lineage and partition columns.

    Nothing is parsed on purpose (`acq_time` arrives unpadded, `"34"` means 00:34). Typing happens in silver.
    """

    latitude: pl.String = pa.Field(nullable=True, description="Pixel center latitude")
    longitude: pl.String = pa.Field(nullable=True, description="Pixel center longitude")
    bright_ti4: pl.String = pa.Field(nullable=True, description="I-4 brightness temperature, K")
    scan: pl.String = pa.Field(nullable=True, description="Along-scan pixel size, km")
    track: pl.String = pa.Field(nullable=True, description="Along-track pixel size, km")
    acq_date: pl.String = pa.Field(description="Acquisition date, UTC, YYYY-MM-DD (partition)")
    acq_time: pl.String = pa.Field(nullable=True, description="Acquisition time, UTC, HHMM, leading zeros may be missing")
    satellite: pl.String = pa.Field(nullable=True, description="Satellite code as sent by the API")
    instrument: pl.String = pa.Field(nullable=True, description="Instrument, VIIRS")
    confidence: pl.String = pa.Field(nullable=True, description="Categorical l/n/h for VIIRS")
    version: pl.String = pa.Field(nullable=True, description="Product version, e.g. 2.0NRT")
    bright_ti5: pl.String = pa.Field(nullable=True, description="I-5 brightness temperature, K")
    frp: pl.String = pa.Field(nullable=True, description="Fire radiative power, MW")
    daynight: pl.String = pa.Field(nullable=True, description="D or N")
    type: pl.String = pa.Field(
        nullable=True,
        description="Detection type (SP only; null in NRT): 0 vegetation fire, 1 volcano, 2 other static land, 3 offshore",
        metadata={"optional": True},
    )

    day_range: pl.Int16 = pa.Field(description="Number of days requested", metadata={"lineage": True})
    requested_at: pl.Datetime(time_unit="us", time_zone="UTC") = pa.Field(description="Request time, UTC", metadata={"lineage": True})
    source: pl.String = pa.Field(description="FIRMS source id, e.g. VIIRS_NOAA20_NRT (partition)", metadata={"lineage": True})
    start_date: pl.Date = pa.Field(description="First day requested", metadata={"lineage": True})

    class Config:
        """
        Table identity and layout.
        """

        name = "bronze.firms_viirs"
        metadata = {"version": 1, "partition_by": ("source", "acq_date")}
