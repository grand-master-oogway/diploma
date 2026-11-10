"""
Tests for the probe (no network).
"""

import json
import re
from datetime import UTC, date, datetime

from firms_ua.common.errors import FirmsError
from firms_ua.common.windows import Window
from firms_ua.firms_api.client import parse_availability
from firms_ua.firms_api.models import FirmsResponse, KeyStatus
from firms_ua.ops.probe import cost_windows, format_report, probe_windows, run_probe
from firms_ua.storage.local import LocalStorage

AVAILABILITY = (
    "data_id,min_date,max_date\n"
    "MODIS_NRT,2026-09-01,2026-11-10\n"
    "VIIRS_NOAA20_NRT,2026-08-01,2026-11-10\n"
    "VIIRS_NOAA20_SP,2018-04-01,2026-07-31\n"
    "VIIRS_NOAA21_NRT,2024-01-17,2026-11-10\n"
    "VIIRS_SNPP_NRT,2026-08-01,2026-11-02\n"
)
ANY = re.compile(r".*")
TODAY = date(2026, 11, 10)


def test_probe_windows_cover_the_questions() -> None:
    """
    Retention, boundary, overlap and gap requests are chosen from the availability data.
    """
    chosen = {(p, w.source, w.start) for p, w in probe_windows(parse_availability(AVAILABILITY.encode()), TODAY)}
    assert ("nrt-retention-3m", "VIIRS_NOAA20_NRT", date(2026, 8, 12)) in chosen
    assert ("nrt-first-day", "VIIRS_NOAA20_NRT", date(2026, 8, 1)) in chosen
    assert ("nrt-day-before-first", "VIIRS_NOAA20_NRT", date(2026, 7, 31)) in chosen
    assert ("nrt-over-sp-days", "VIIRS_NOAA21_NRT", date(2025, 7, 15)) in chosen
    assert ("gap-refetch", "VIIRS_SNPP_SP", date(2024, 7, 15)) in chosen
    assert len({w for _, w in probe_windows([], TODAY)}) > 10  # still works without availability data


class Meter:
    """
    A fake key budget: every request costs its day range, every status read costs 1.
    """

    def __init__(self) -> None:
        """
        Start at zero.
        """
        self.used = 0

    def status(self) -> KeyStatus:
        """
        Return the counter, then count this call.
        """
        current = self.used
        self.used += 1
        return KeyStatus(current, 5000, "10 minutes")

    def fetch(self, window: Window) -> FirmsResponse:
        """
        Pretend to fetch; fail for one specific window.
        """
        self.used += window.day_range
        if window.source == "VIIRS_NOAA20_NRT" and window.start == date(2026, 7, 31):
            raise FirmsError("HTTP 400 for https://x/***: 'out of range'", http_status=400)
        return FirmsResponse(b"latitude\n1\n2\n", 200, "https://x/***", 2)


def test_run_probe_measures_cost_saves_files_and_survives_failures(tmp_path) -> None:
    """
    Costs are derived from the counter, failures are recorded, and files are saved without any key.
    """
    store = LocalStorage(tmp_path)
    meter = Meter()
    report = run_probe(
        store,
        get_availability=lambda: AVAILABILITY.encode(),
        get_status=meter.status,
        fetcher=meter.fetch,
        now=lambda: datetime(2026, 11, 10, 12, tzinfo=UTC),
    )
    assert report.status_call_cost == 1
    assert report.cost_per_1day_request == 1
    assert report.cost_per_5day_request == 5
    assert report.transaction_limit == 5000
    failed = [w for w in report.windows if not w.ok]
    assert [(w.purpose, w.http_status) for w in failed] == [("nrt-day-before-first", 400)]
    assert len([w for w in report.windows if w.purpose == "cost"]) == len(sum(cost_windows(), []))

    keys = store.list_keys("firms_meta/probe/20261110T120000Z/")
    assert "firms_meta/probe/20261110T120000Z/availability.csv" in keys
    assert "firms_meta/probe/20261110T120000Z/summary.json" in keys
    summary = json.loads(store.get("firms_meta/probe/20261110T120000Z/summary.json"))
    assert summary["cost_per_5day_request"] == 5
    text = format_report(report)
    assert "FAILED http=400" in text
    assert "VIIRS_SNPP_NRT" in text


def test_counter_reset_gives_unknown_cost(tmp_path) -> None:
    """
    If the budget counter resets during the measurement, the cost is reported as unknown, not negative.
    """
    meter = Meter()
    calls = {"n": 0}

    def status() -> KeyStatus:
        calls["n"] += 1
        if calls["n"] == 4:  # the read right after the 1-day requests: the interval rolled over
            meter.used = 0
        return meter.status()

    report = run_probe(LocalStorage(tmp_path), get_availability=lambda: AVAILABILITY.encode(), get_status=status, fetcher=meter.fetch)
    assert None in (report.cost_per_1day_request, report.cost_per_5day_request)
