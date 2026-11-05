"""FIRMS area API client."""

import logging
import random
import time
from dataclasses import dataclass

import requests

from firms_ua.windows import Window

log = logging.getLogger(__name__)

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
EXPECTED_COLUMNS = frozenset(
    {
        "latitude", "longitude", "bright_ti4", "scan", "track", "acq_date", "acq_time",
        "satellite", "confidence", "bright_ti5", "frp", "daynight",
    }
)  # fmt: skip


class FirmsError(Exception):
    """Non-retryable FIRMS failure."""


@dataclass(frozen=True)
class FirmsResponse:
    """Raw API response; `content` is unchanged bytes."""

    content: bytes
    status: int
    url_redacted: str
    row_count: int


# TODO decide which exact data it should fetch, sp - standart processing or nrt - near real-time
# sp and nrt can override each other and itshould be handled somehow
def build_url(key: str, window: Window, bbox: tuple[float, float, float, float]) -> str:
    """Build the area URL (contains the secret key; never log it)."""
    area = ",".join(str(v) for v in bbox)
    return f"{BASE_URL}/{key}/{window.source}/{area}/{window.day_range}/{window.start:%Y-%m-%d}"


# TODO handle it via key vaults in gcp
def redact(url: str, key: str) -> str:
    """Replace the MAP_KEY in `url`."""
    return url.replace(key, "***")


def validate_csv(content: bytes) -> int:
    """Check the header row and return the data row count.

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


def fetch(
    key: str,
    window: Window,
    bbox: tuple[float, float, float, float],
    *,
    timeout: float = 60.0,
    max_retries: int = 5,
    session: requests.Session | None = None,
) -> FirmsResponse:
    """Fetch one window, retrying only network errors, 429 and 5xx."""
    http = session or requests.Session()
    url = build_url(key, window, bbox)
    safe = redact(url, key)
    for attempt in range(max_retries + 1):
        try:
            r = http.get(url, timeout=timeout)
        except requests.RequestException as e:
            err = f"{type(e).__name__} for {safe}"
        else:
            if r.status_code == 200:
                return FirmsResponse(r.content, 200, safe, validate_csv(r.content))
            if r.status_code != 429 and r.status_code < 500:
                msg = f"HTTP {r.status_code} for {safe}: {redact(r.text[:200], key)!r}"
                raise FirmsError(msg)
            err = f"HTTP {r.status_code} for {safe}"
        if attempt == max_retries:
            msg = f"giving up after {attempt + 1} attempts: {err}"
            raise FirmsError(msg)
        delay = min(60.0, 2.0**attempt) * random.uniform(0.5, 1.5)  # noqa: S311
        log.warning("%s; retry in %.1fs", err, delay)
        time.sleep(delay)
    raise AssertionError  # pragma: no cover
