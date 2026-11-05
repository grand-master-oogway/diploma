"""
Bronze table definitions.
"""

from typing import ClassVar

import polars as pl

from firms_ua.datacatalog.base import Column, Table

S = pl.String


class FirmsBronze(Table):
    """
    Raw FIRMS VIIRS detections: every API column as a string, plus lineage.

    Nothing is parsed here on purpose (for example `acq_time` arrives unpadded, `"34"` means 00:34).
    Typing and cleaning happen in silver.
    """

    name = "firms_viirs"
    layer = "bronze"
    version = 1
    partition_by = ("source",)  # a directory only, not a column in the file

    raw_columns: ClassVar[tuple[Column, ...]] = (
        Column("latitude", S, "Pixel center latitude"),
        Column("longitude", S, "Pixel center longitude"),
        Column("bright_ti4", S, "I-4 brightness temperature, K"),
        Column("scan", S, "Along-scan pixel size, km"),
        Column("track", S, "Along-track pixel size, km"),
        Column("acq_date", S, "Acquisition date, UTC, YYYY-MM-DD"),
        Column("acq_time", S, "Acquisition time, UTC, HHMM, leading zeros may be missing"),
        Column("satellite", S, "Satellite code as sent by the API (encoding varies)"),
        Column("instrument", S, "Instrument, VIIRS"),
        Column("confidence", S, "Categorical l/n/h for VIIRS"),
        Column("version", S, "Product version, e.g. 2.0NRT"),
        Column("bright_ti5", S, "I-5 brightness temperature, K"),
        Column("frp", S, "Fire radiative power, MW"),
        Column("daynight", S, "D or N"),
    )
    lineage_columns: ClassVar[tuple[Column, ...]] = (
        Column("day_range", pl.Int16, "Number of days requested", nullable=False),
        Column("start_date", pl.Date, "First day requested", nullable=False),
        Column("requested_at", pl.Datetime("us", "UTC"), "Request time, UTC", nullable=False),
    )
    columns = raw_columns + lineage_columns

    @classmethod
    def raw_column_names(cls) -> list[str]:
        """
        Return the names of the columns that come from the API.
        """
        return [c.name for c in cls.raw_columns]
