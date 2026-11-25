"""
Bronze profiling: versions, overpass hours, active days per cell.
"""

from bronze_factory import bronze, nrt
from firms_ua.ops.bronze_profile import active_days, hours, versions


def test_versions_hours_and_active_days() -> None:
    """
    Profiles count per source and version, per UTC hour, and per H3 r9 cell's distinct days.
    """
    df = bronze({"acq_time": "51"}, {"acq_time": "1040", "acq_date": "2025-07-16"}, nrt(acq_time="2252")).lazy()
    assert [(v["source"], v["version"], v["rows"]) for v in versions(df)] == [
        ("VIIRS_NOAA20_NRT", "2.0NRT", 1),
        ("VIIRS_NOAA20_SP", "2", 2),
    ]
    by_hour = hours(df)
    assert by_hour["VIIRS_NOAA20_SP"][0] == 1
    assert by_hour["VIIRS_NOAA20_SP"][10] == 1
    assert by_hour["VIIRS_NOAA20_NRT"][22] == 1
    assert active_days(df)["2025"] == {">=5": 0, ">=10": 0, ">=20": 0, ">=30": 0, ">=50": 0, ">=100": 0, ">=200": 0, "cells": 1}
