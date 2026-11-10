"""
Smoke test for a new environment: can this identity reach FIRMS, the secret and the buckets it should use?

The test objects are tiny files under `_smoke/` (buckets never allow deletes, so they stay).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from firms_ua.firms_api.client import parse_availability
from firms_ua.storage.base import Storage

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckResult:
    """
    One smoke check and what happened.
    """

    name: str
    ok: bool
    detail: str


def run_smoke(
    *,
    get_key: Callable[[], str],
    get_availability: Callable[[str], bytes],
    open_layer: Callable[[str], Storage],
    checks: list[tuple[str, str]],
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> list[CheckResult]:
    """
    Run all checks; a failing check is reported, it does not stop the others.

    Args:
        get_key: Returns the MAP_KEY (from the environment or Secret Manager).
        get_availability: Calls the FIRMS availability endpoint with the key.
        open_layer: Returns the storage of a layer.
        checks: `(layer, mode)` pairs; mode `rw` writes then reads back, `w` only writes (for create-only identities).
        now: Clock (injectable).
    """
    results: list[CheckResult] = []
    key: str | None = None
    try:
        key = get_key()
        results.append(CheckResult("map key", True, f"found ({len(key)} characters)"))
    except Exception as e:  # noqa: BLE001  (any failure is a failed check; the message cannot contain the key)
        results.append(CheckResult("map key", False, f"{type(e).__name__}: {e}"))
    if key is not None:
        try:
            sources = [a for a in parse_availability(get_availability(key)) if a.data_id.startswith("VIIRS")]
            results.append(CheckResult("FIRMS availability", True, f"HTTP 200, {len(sources)} VIIRS sources"))
        except Exception as e:  # noqa: BLE001
            detail = str(e).replace(key, "***")[:200]
            results.append(CheckResult("FIRMS availability", False, f"{type(e).__name__}: {detail}"))

    stamp = now().strftime("%Y%m%dT%H%M%S%fZ")
    for layer, mode in checks:
        name = f"bucket {layer} ({'write+read' if mode == 'rw' else 'write only'})"
        try:
            store = open_layer(layer)
            object_key = f"_smoke/{stamp}.txt"
            store.put_new(object_key, b"smoke")
            if mode == "rw" and store.get(object_key) != b"smoke":
                results.append(CheckResult(name, False, "read-back differs"))
                continue
            results.append(CheckResult(name, True, object_key))
        except Exception as e:  # noqa: BLE001
            results.append(CheckResult(name, False, f"{type(e).__name__}: {str(e)[:200]}"))
    return results
