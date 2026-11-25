"""
Builds bronze frames for silver tests (string FIRMS columns, lineage, `acq_date` partition).
"""

from datetime import UTC, datetime
from typing import Final

import polars as pl

from firms_ua.datacatalog.bronze import FirmsBronze

FETCHED: Final = datetime(2026, 11, 10, 16, 0, tzinfo=UTC)
KYIV: Final = (50.45, 30.52)
_DEFAULTS: Final = {
    "latitude": "50.45",
    "longitude": "30.52",
    "bright_ti4": "330.5",
    "scan": "0.4",
    "track": "0.5",
    "acq_date": "2025-07-15",
    "acq_time": "51",
    "satellite": "N20",
    "instrument": "VIIRS",
    "confidence": "n",
    "version": "2",
    "bright_ti5": "290.1",
    "frp": "3.5",
    "daynight": "N",
    "type": "0",
    "day_range": 1,
    "requested_at": FETCHED,
    "source": "VIIRS_NOAA20_SP",
    "start_date": None,
}


def bronze(*rows: dict[str, object]) -> pl.DataFrame:
    """
    Return a bronze frame with one row per dict; unspecified columns take `_DEFAULTS`.
    """
    records = [{**_DEFAULTS, **row} for row in rows]
    for r in records:
        r["start_date"] = r["start_date"] or datetime.fromisoformat(str(r["acq_date"])).date()
    return (
        pl.DataFrame(records, schema=FirmsBronze.polars_schema(), orient="row")
        if records
        else pl.DataFrame(schema=FirmsBronze.polars_schema())
    )


def nrt(**row: object) -> dict[str, object]:
    """
    Return an NRT row (no `type`, NRT version and source).
    """
    return {"version": "2.0NRT", "source": "VIIRS_NOAA20_NRT", "type": None, **row}
