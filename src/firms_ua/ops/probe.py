"""
Probe: measure what FIRMS actually serves before a big backfill.

It answers four questions and saves every raw response and a JSON summary under `firms_meta/probe/<timestamp>/` in the
raw storage (the MAP_KEY is never stored):

1. which date range each source has (availability endpoint);
2. how far back NRT can be requested, and whether NRT overlaps SP;
3. how many transactions one 1-day and one 5-day request cost against the key's budget;
4. whether an empty day (S-NPP on 2024-07-15) stays empty when fetched again.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta

from firms_ua.common.errors import FirmsError
from firms_ua.common.windows import Window
from firms_ua.firms_api.client import parse_availability
from firms_ua.firms_api.models import Availability, FirmsResponse, KeyStatus
from firms_ua.storage.base import Storage

log = logging.getLogger(__name__)

NRT_SOURCES = ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT")
_SP = "VIIRS_NOAA20_SP"
_GAP_DAY = date(2024, 7, 15)
_OVERLAP_DAY = date(2025, 7, 15)


@dataclass(frozen=True)
class WindowResult:
    """
    Outcome of one probe request.
    """

    purpose: str
    source: str
    start: date
    day_range: int
    ok: bool
    rows: int | None
    http_status: int | None
    error: str | None


@dataclass(frozen=True)
class ProbeReport:
    """
    Everything the probe measured.
    """

    started_at: datetime
    availability: list[Availability]
    transaction_limit: int
    status_call_cost: int | None
    cost_per_1day_request: float | None
    cost_per_5day_request: float | None
    windows: list[WindowResult]


def _day(source: str, start: date, purpose: str, days: int = 1) -> tuple[str, Window]:
    return purpose, Window(source, start, days)


def probe_windows(availability: list[Availability], today: date) -> list[tuple[str, Window]]:
    """
    Choose the requests that answer questions 2 and 4 (cost windows are separate).

    Pure: the same availability and date always give the same list.
    """
    by_id = {a.data_id: a for a in availability}
    out: list[tuple[str, Window]] = []
    for source in NRT_SOURCES:
        for months, back in ((3, 90), (4, 120), (5, 150)):
            out.append(_day(source, today - timedelta(days=back), f"nrt-retention-{months}m"))
        first = by_id.get(source)
        if first is not None:
            out.append(_day(source, first.min_date, "nrt-first-day"))
            out.append(_day(source, first.min_date - timedelta(days=1), "nrt-day-before-first"))
        out.append(_day(source, _OVERLAP_DAY, "nrt-over-sp-days"))
    out += [_day("VIIRS_SNPP_SP", _GAP_DAY + timedelta(days=d), "gap-neighbour") for d in (-1, 0, 1)]
    out += [
        _day(_SP, _GAP_DAY, "gap-other-satellite"),
        _day("VIIRS_NOAA21_SP", _GAP_DAY, "gap-other-satellite"),
        _day("VIIRS_SNPP_SP", _GAP_DAY, "gap-refetch"),
    ]
    return out


def cost_windows() -> tuple[list[Window], list[Window]]:
    """
    Windows used to measure the transaction cost: three 1-day and three 5-day requests of one SP source.
    """
    one = [Window(_SP, date(2025, 7, 16) + timedelta(days=i), 1) for i in range(3)]
    five = [Window(_SP, date(2025, 7, 1) + timedelta(days=5 * i), 5) for i in range(3)]
    return one, five


def run_probe(
    store: Storage,
    *,
    get_availability: Callable[[], bytes],
    get_status: Callable[[], KeyStatus],
    fetcher: Callable[[Window], FirmsResponse],
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ProbeReport:
    """
    Run all probe requests, save raw responses and the summary, and return the report.

    A request that fails is recorded in the report; it does not stop the probe.
    """
    started = now()
    prefix = f"firms_meta/probe/{started:%Y%m%dT%H%M%SZ}"

    availability_bytes = get_availability()
    store.put_new(f"{prefix}/availability.csv", availability_bytes)
    availability = parse_availability(availability_bytes)

    results: list[WindowResult] = []

    def attempt(purpose: str, window: Window) -> bool:
        try:
            resp = fetcher(window)
        except FirmsError as e:
            results.append(WindowResult(purpose, window.source, window.start, window.day_range, False, None, e.http_status, str(e)[:300]))
            return False
        name = f"{purpose}__{window.source}__{window.start}_d{window.day_range}.csv"
        store.put_new(f"{prefix}/windows/{name}", resp.content)
        results.append(WindowResult(purpose, window.source, window.start, window.day_range, True, resp.row_count, resp.status, None))
        return True

    # Cost first, while the counter is quiet. Reading the status costs a transaction itself, so measure that too.
    first = get_status()
    second = get_status()
    status_cost = second.current_transactions - first.current_transactions

    def per_request(windows: list[Window]) -> float | None:
        before = get_status().current_transactions
        for window in windows:
            attempt("cost", window)
        after = get_status().current_transactions
        used = after - before - status_cost
        return used / len(windows) if used >= 0 else None  # a negative value means the counter reset meanwhile

    one_day, five_day = cost_windows()
    cost_one = per_request(one_day)
    cost_five = per_request(five_day)

    for purpose, window in probe_windows(availability, started.date()):
        attempt(purpose, window)

    report = ProbeReport(
        started_at=started,
        availability=availability,
        transaction_limit=second.transaction_limit,
        status_call_cost=status_cost,
        cost_per_1day_request=cost_one,
        cost_per_5day_request=cost_five,
        windows=results,
    )
    store.put_new(f"{prefix}/summary.json", json.dumps(asdict(report), default=str, indent=2).encode())
    log.info("probe saved under %s", prefix)
    return report


def format_report(report: ProbeReport) -> str:
    """
    Render the report as plain text for the terminal.
    """
    lines = ["Availability (VIIRS sources):"]
    lines += [f"  {a.data_id:<18} {a.min_date} .. {a.max_date}" for a in report.availability if a.data_id.startswith("VIIRS")]
    lines += [
        "",
        f"Key budget: {report.transaction_limit} transactions per interval; a status call costs {report.status_call_cost}.",
        f"Cost per request: 1-day = {report.cost_per_1day_request}, 5-day = {report.cost_per_5day_request} transactions.",
        "",
        "Requests (purpose, source, start+days -> result):",
    ]
    for w in report.windows:
        result = f"{w.rows} rows" if w.ok else f"FAILED http={w.http_status}: {w.error}"
        lines.append(f"  {w.purpose:<22} {w.source:<17} {w.start}+{w.day_range} -> {result}")
    return "\n".join(lines)
