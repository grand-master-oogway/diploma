"""
Silver tables.
"""

import pandera.polars as pa
import polars as pl

from firms_ua.datacatalog_core.parquet_table import ParquetTable
from firms_ua.silver.labels import CONFIDENCES, DAYNIGHTS, PRODUCTS, SATELLITES


class FirmsSilver(ParquetTable):
    """
    Typed FIRMS VIIRS detections: one row per detection of the latest response, SP and NRT in one schema.

    Questionable rows are flagged, not deleted (filtering is a gold parameter). Only detections farther than the border
    buffer outside Ukraine and exact repeats are dropped. A point is the pixel center, not the fire's location.
    """

    detection_id: pl.String = pa.Field(description="SHA-256 (32 hex) of source, latitude, longitude, acq_date and acq_time as sent")
    acq_time: pl.Datetime(time_unit="us", time_zone="UTC") = pa.Field(description="Acquisition time, UTC (minute precision)")
    acq_date_kyiv: pl.Date = pa.Field(description="Calendar date of acq_time in Europe/Kyiv (gold aggregation day)")
    latitude: pl.Float64 = pa.Field(description="Pixel center latitude")
    longitude: pl.Float64 = pa.Field(description="Pixel center longitude")
    h3_r7: pl.UInt64 = pa.Field(description="H3 cell, resolution 7 (about 5.2 km2)")
    h3_r9: pl.UInt64 = pa.Field(description="H3 cell, resolution 9 (about 0.1 km2); not for publishing")
    satellite: pl.Enum(SATELLITES) = pa.Field(description="Satellite, from the FIRMS source id")
    product: pl.Enum(PRODUCTS) = pa.Field(description="sp (Standard Processing) or nrt (Near Real-Time), from version")
    collection: pl.Int8 = pa.Field(description="VIIRS collection, from version")
    pass_id: pl.String = pa.Field(description="Overpass: satellite and first acq_time of the pass (gap > 20 min starts a new one)")
    bright_ti4: pl.Float32 = pa.Field(description="I-4 brightness temperature, K")
    bright_ti5: pl.Float32 = pa.Field(description="I-5 brightness temperature, K")
    frp: pl.Float32 = pa.Field(description="Fire radiative power, MW")
    scan: pl.Float32 = pa.Field(description="Along-scan pixel size, km")
    track: pl.Float32 = pa.Field(description="Along-track pixel size, km")
    pixel_area_km2: pl.Float32 = pa.Field(description="scan x track")
    confidence: pl.Enum(CONFIDENCES) = pa.Field(description="From FIRMS l/n/h")
    daynight: pl.Enum(DAYNIGHTS) = pa.Field(description="From FIRMS D/N")
    type: pl.Int8 = pa.Field(nullable=True, description="SP only (null for NRT): 0 vegetation, 1 volcano, 2 static land, 3 offshore")
    in_ukraine: pl.Boolean = pa.Field(description="Inside the border polygon")
    border_distance_km: pl.Float32 = pa.Field(description="Distance to the border polygon, 0 inside")
    is_persistent_hotspot: pl.Boolean = pa.Field(description="h3_r9 cell active on many of the previous 365 days")
    is_preferred: pl.Boolean = pa.Field(description="Use this row: SP if the satellite has SP that day, else NRT")
    flag_invalid_brightness: pl.Boolean = pa.Field(
        description="bright_ti4 or bright_ti5 is <= 0 K (a FIRMS fill value, not a temperature); kept, not dropped"
    )
    source: pl.String = pa.Field(description="FIRMS source id", metadata={"lineage": True})
    fetched_at: pl.Datetime(time_unit="us", time_zone="UTC") = pa.Field(
        description="Request time of the bronze response", metadata={"lineage": True}
    )
    run_id: pl.String = pa.Field(description="Dagster run that built the partition", metadata={"lineage": True})
    acq_date: pl.Date = pa.Field(description="Acquisition date, UTC (partition)")

    class Config:
        """
        Table identity and layout.
        """

        name = "silver.firms_detections"
        metadata = {"version": 1, "partition_by": ("acq_date",)}


class H3DailyActivity(ParquetTable):
    """
    Preferred detections per H3 r9 cell and UTC day (cells with none are absent); the input of the persistent-hotspot flag.
    """

    h3_r9: pl.UInt64 = pa.Field(description="H3 cell, resolution 9")
    detections: pl.UInt32 = pa.Field(description="Preferred detections in the cell that day")
    acq_date: pl.Date = pa.Field(description="Acquisition date, UTC (partition)")

    class Config:
        """
        Table identity and layout.
        """

        name = "silver.h3_r9_daily_activity"
        metadata = {"version": 1, "partition_by": ("acq_date",)}
