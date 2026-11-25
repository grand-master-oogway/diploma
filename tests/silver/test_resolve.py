"""
Latest response, exact repeats and the SP-over-NRT day rule.
"""

from datetime import UTC, datetime

import polars as pl

from bronze_factory import FETCHED, bronze, nrt
from firms_ua.silver.parse import parse_bronze
from firms_ua.silver.resolve import drop_repeats, latest_responses, mark_preferred

LATER = datetime(2026, 11, 20, tzinfo=UTC)


def test_latest_response_wins_per_source_and_day() -> None:
    """
    Latest response wins per source and day.
    """
    df = bronze(
        {"latitude": "50.1"},
        {"latitude": "50.2"},
        {"latitude": "50.3", "requested_at": LATER},
        {"acq_date": "2025-07-16", "latitude": "50.4"},
        nrt(latitude="50.5"),
    )
    out = latest_responses(df)
    assert sorted(out["latitude"].to_list()) == ["50.3", "50.4", "50.5"]
    assert set(out.filter(pl.col("acq_date") == "2025-07-16")["requested_at"]) == {FETCHED}


def test_drop_repeats_counts_removed_rows() -> None:
    """
    Drop repeats counts removed rows.
    """
    typed = parse_bronze(bronze({}, {}, {"acq_time": "52"}))
    out, removed = drop_repeats(typed)
    assert (out.height, removed) == (2, 1)


def test_sp_is_preferred_on_days_with_sp_else_nrt() -> None:
    """
    Sp is preferred on days with sp else nrt.
    """
    typed = parse_bronze(
        bronze(
            {},  # noaa20 SP on 07-15
            nrt(),  # noaa20 NRT on 07-15: SP exists that day
            nrt(acq_date="2025-07-16"),  # noaa20 NRT, no SP that day
            {"source": "VIIRS_NOAA21_SP", "version": "2"},  # other satellite, SP
            {"source": "VIIRS_NOAA21_NRT", "version": "2.0NRT", "type": None, "acq_date": "2025-07-16"},
        )
    )
    assert mark_preferred(typed)["is_preferred"].to_list() == [True, False, True, True, True]
