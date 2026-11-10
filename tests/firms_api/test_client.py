"""
Tests for the FIRMS client: area fetch, availability and key status (no network).
"""

import re
from datetime import UTC, date, datetime

import pytest
import responses

from firms_ua.common.errors import FirmsError
from firms_ua.common.windows import Window
from firms_ua.firms_api.client import fetch, fetch_availability, fetch_key_status, parse_availability
from firms_ua.firms_api.models import Availability, KeyStatus

HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
ROW = "50.1,30.2,330.1,0.4,0.4,2024-03-01,0007,N20,VIIRS,n,2.0NRT,290.1,1.2,N\n"
W = Window("VIIRS_NOAA20_NRT", date(2024, 3, 1), 1)
BBOX = (22.1, 44.4, 40.2, 52.4)
ANY = re.compile(r".*")
T0 = datetime(2024, 3, 2, tzinfo=UTC)


@responses.activate
def test_header_only_is_valid_zero_rows() -> None:
    """
    An empty but valid response has row_count 0.
    """
    responses.add(responses.GET, ANY, body=HEADER)
    assert fetch("K", W, BBOX, max_retries=0).row_count == 0


@responses.activate
def test_bad_body_raises() -> None:
    """
    A 200 with a non-CSV body is an error.
    """
    responses.add(responses.GET, ANY, body="Invalid MAP_KEY")
    with pytest.raises(FirmsError):
        fetch("K", W, BBOX, max_retries=0)


@responses.activate
def test_400_not_retried() -> None:
    """
    A 400 is surfaced immediately.
    """
    responses.add(responses.GET, ANY, status=400, body="bad")
    with pytest.raises(FirmsError, match="HTTP 400"):
        fetch("K", W, BBOX, max_retries=3)
    assert len(responses.calls) == 1


AVAILABILITY = (
    "data_id,min_date,max_date\n"
    "MODIS_NRT,2026-09-01,2026-11-10\n"
    "VIIRS_NOAA20_NRT,2026-08-01,2026-11-10\n"
    "VIIRS_NOAA20_SP,2018-04-01,2026-07-31\n"
    "VIIRS_NOAA21_NRT,2024-01-17,2026-11-10\n"
    "VIIRS_SNPP_NRT,2026-08-01,2026-11-02\n"
)
ANY = re.compile(r".*")


def test_parse_availability() -> None:
    """
    Rows become typed ranges; a non-availability body is rejected.
    """
    rows = parse_availability(AVAILABILITY.encode())
    assert rows[1] == Availability("VIIRS_NOAA20_NRT", date(2026, 8, 1), date(2026, 11, 10))
    with pytest.raises(FirmsError):
        parse_availability(b"Invalid MAP_KEY")


@responses.activate
def test_availability_and_status_calls_redact_the_key() -> None:
    """
    Both calls work, and errors never contain the key.
    """
    responses.add(responses.GET, ANY, body=AVAILABILITY)
    assert fetch_availability("SECRETKEY", max_retries=0) == AVAILABILITY.encode()
    responses.replace(
        responses.GET, ANY, body='{"transaction_limit": 5000, "current_transactions": 7, "transaction_interval": "10 minutes"}'
    )
    assert fetch_key_status("SECRETKEY", max_retries=0) == KeyStatus(7, 5000, "10 minutes")
    responses.replace(responses.GET, ANY, status=400, body="bad SECRETKEY")
    with pytest.raises(FirmsError) as info:
        fetch_key_status("SECRETKEY", max_retries=0)
    assert "SECRETKEY" not in str(info.value)
    responses.replace(responses.GET, ANY, body="not json SECRETKEY")
    with pytest.raises(FirmsError) as bad_body:
        fetch_key_status("SECRETKEY", max_retries=0)
    assert "SECRETKEY" not in str(bad_body.value)
