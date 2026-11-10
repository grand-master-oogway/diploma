"""
FIRMS API client: area downloads, data availability and MAP_KEY status.

The MAP_KEY is part of every URL, so every error message built here has the key redacted.
"""

import json
import logging
import random
import time
from datetime import date

import requests

from firms_ua.common.errors import FirmsError
from firms_ua.common.windows import Window
from firms_ua.datacatalog.bronze import FirmsBronze
from firms_ua.firms_api.models import Availability, FirmsResponse, KeyStatus

log = logging.getLogger(__name__)

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
AVAILABILITY_URL = "https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv"
KEY_STATUS_URL = "https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/"
EXPECTED_COLUMNS = (
    frozenset(FirmsBronze.column_names())
    - frozenset(FirmsBronze.columns_with_metadata("lineage"))
    - frozenset(FirmsBronze.columns_with_metadata("optional"))
)


# TODO decide which exact data it should fetch, sp - standart processing or nrt - near real-time
# sp and nrt can override each other and itshould be handled somehow
def build_url(key: str, window: Window, bbox: tuple[float, float, float, float]) -> str:
    """
    Build the area URL (contains the secret key; never log it).
    """
    area = ",".join(str(v) for v in bbox)
    return f"{BASE_URL}/{key}/{window.source}/{area}/{window.day_range}/{window.start:%Y-%m-%d}"


def redact(url: str, key: str) -> str:
    """
    Replace the MAP_KEY in `url`.
    """
    return url.replace(key, "***")


def validate_csv(content: bytes) -> int:
    """
    Check the header row and return the data row count.

    Raises:
        FirmsError: If the body is not a FIRMS CSV (a 200 may carry an error message).
    """
    text = content.decode("utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        msg = "empty body"
        raise FirmsError(msg)
    header = {c.strip() for c in lines[0].split(",")}
    missing = EXPECTED_COLUMNS - header
    if missing:
        msg = f"unexpected CSV header, missing {sorted(missing)}; body starts: {text[:200]!r}"
        raise FirmsError(msg)
    return len(lines) - 1


def _get(
    url: str,
    key: str,
    *,
    timeout: float,
    max_retries: int,
    session: requests.Session | None,
) -> requests.Response:
    """
    GET `url`, retrying only network errors, 429 and 5xx; return the 200 response.

    Raises:
        FirmsError: On a non-retryable status or when retries run out (messages never contain the key).
    """
    http = session or requests.Session()
    safe = redact(url, key)
    status: int | None = None
    for attempt in range(max_retries + 1):
        try:
            r = http.get(url, timeout=timeout)
        except requests.RequestException as e:
            status = None
            err = f"{type(e).__name__} for {safe}"
        else:
            status = r.status_code
            if status == 200:
                return r
            if status != 429 and status < 500:
                msg = f"HTTP {status} for {safe}: {redact(r.text[:200], key)!r}"
                raise FirmsError(msg, http_status=status)
            err = f"HTTP {status} for {safe}"
        if attempt == max_retries:
            msg = f"giving up after {attempt + 1} attempts: {err}"
            raise FirmsError(msg, http_status=status)
        delay = min(60.0, 2.0**attempt) * random.uniform(0.5, 1.5)  # noqa: S311
        log.warning("%s; retry in %.1fs", err, delay)
        time.sleep(delay)
    raise AssertionError  # pragma: no cover


def fetch(
    key: str,
    window: Window,
    bbox: tuple[float, float, float, float],
    *,
    timeout: float = 60.0,
    max_retries: int = 5,
    session: requests.Session | None = None,
) -> FirmsResponse:
    """
    Fetch one window, retrying only network errors, 429 and 5xx.
    """
    url = build_url(key, window, bbox)
    r = _get(url, key, timeout=timeout, max_retries=max_retries, session=session)
    try:
        rows = validate_csv(r.content)
    except FirmsError as e:  # the error text is stored in the ingestion log: keep the key out of it
        raise FirmsError(redact(str(e), key), http_status=200) from None
    return FirmsResponse(r.content, 200, redact(url, key), rows)


def parse_availability(content: bytes) -> list[Availability]:
    """
    Parse the data-availability CSV (`data_id,min_date,max_date`).

    Raises:
        FirmsError: If the body is not that CSV.
    """
    lines = content.decode("utf-8", errors="replace").splitlines()
    if not lines or [c.strip() for c in lines[0].split(",")] != ["data_id", "min_date", "max_date"]:
        msg = f"unexpected availability response: {content[:120]!r}"
        raise FirmsError(msg)
    rows = []
    for line in lines[1:]:
        if line.strip():
            data_id, first, last = (c.strip() for c in line.split(","))
            rows.append(Availability(data_id, date.fromisoformat(first), date.fromisoformat(last)))
    return rows


def fetch_availability(
    key: str,
    *,
    timeout: float = 60.0,
    max_retries: int = 3,
    session: requests.Session | None = None,
) -> bytes:
    """
    Fetch the unchanged availability CSV for all sources.
    """
    url = f"{AVAILABILITY_URL}/{key}/all"
    return _get(url, key, timeout=timeout, max_retries=max_retries, session=session).content


def fetch_key_status(
    key: str,
    *,
    timeout: float = 60.0,
    max_retries: int = 3,
    session: requests.Session | None = None,
) -> KeyStatus:
    """
    Read the MAP_KEY's transaction budget.
    """
    url = f"{KEY_STATUS_URL}?MAP_KEY={key}"
    r = _get(url, key, timeout=timeout, max_retries=max_retries, session=session)
    try:
        body = json.loads(r.text)
        return KeyStatus(int(body["current_transactions"]), int(body["transaction_limit"]), str(body["transaction_interval"]))
    except ValueError, KeyError, TypeError:
        msg = f"unexpected key-status response: {redact(r.text[:120], key)!r}"
        raise FirmsError(msg, http_status=200) from None
