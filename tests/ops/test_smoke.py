"""
Tests for the smoke checks (no network).
"""

from datetime import UTC, datetime

from firms_ua.ops.smoke import run_smoke
from firms_ua.storage.base import Storage
from firms_ua.storage.local import LocalStorage

AVAILABILITY = b"data_id,min_date,max_date\nVIIRS_NOAA20_NRT,2026-08-01,2026-11-10\nMODIS_NRT,2026-09-01,2026-11-10\n"
NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)


class DeniedStorage(LocalStorage):
    """
    A storage whose reads and writes are refused, like a bucket the identity cannot use.
    """

    def put_new(self, key: str, data: bytes) -> None:
        """
        Always refuse.
        """
        raise PermissionError("403 forbidden")


def test_smoke_all_pass_and_write_only_layer_is_not_read(tmp_path) -> None:
    """
    `rw` writes and reads back; `w` only writes (a create-only identity could not read it).
    """
    stores: dict[str, Storage] = {"raw": LocalStorage(tmp_path / "raw"), "bronze": LocalStorage(tmp_path / "bronze")}
    reads: list[str] = []
    original_get = stores["bronze"].get
    stores["bronze"].get = lambda key: (reads.append(key), original_get(key))[1]  # type: ignore[method-assign]
    results = run_smoke(
        get_key=lambda: "k" * 32,
        get_availability=lambda key: AVAILABILITY,
        open_layer=stores.__getitem__,
        checks=[("raw", "rw"), ("bronze", "w")],
        now=lambda: NOW,
    )
    assert all(r.ok for r in results), results
    assert [r.name for r in results][:2] == ["map key", "FIRMS availability"]
    assert "1 VIIRS sources" in results[1].detail
    assert stores["raw"].exists("_smoke/20261110T120000000000Z.txt")
    assert reads == []


def test_smoke_reports_failures_and_keeps_going(tmp_path) -> None:
    """
    A refused bucket and a failing FIRMS call are reported; the key never appears in details.
    """

    def availability(key: str) -> bytes:
        raise RuntimeError(f"HTTP 400 for https://x/{key}/all")

    results = run_smoke(
        get_key=lambda: "SECRETKEY",
        get_availability=availability,
        open_layer=lambda layer: DeniedStorage(tmp_path / layer) if layer == "gold" else LocalStorage(tmp_path / layer),
        checks=[("gold", "w"), ("raw", "rw")],
        now=lambda: NOW,
    )
    by_name = {r.name: r for r in results}
    assert not by_name["FIRMS availability"].ok
    assert "SECRETKEY" not in by_name["FIRMS availability"].detail
    assert not by_name["bucket gold (write only)"].ok
    assert "PermissionError" in by_name["bucket gold (write only)"].detail
    assert by_name["bucket raw (write+read)"].ok


def test_smoke_without_key_skips_firms_call() -> None:
    """
    If the key cannot be loaded, that check fails and FIRMS is not called.
    """

    def no_key() -> str:
        raise ValueError("no key configured")

    called: list[str] = []
    results = run_smoke(get_key=no_key, get_availability=lambda k: called.append(k) or b"", open_layer=lambda layer: None, checks=[])  # type: ignore[arg-type,return-value]
    assert [(r.name, r.ok) for r in results] == [("map key", False)]
    assert called == []
