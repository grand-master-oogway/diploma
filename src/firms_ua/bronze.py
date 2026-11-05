"""
Bronze writer: raw bytes + manifest, never overwritten.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from firms_ua import __version__
from firms_ua.firms_client import FirmsResponse
from firms_ua.windows import Window


def _request_dir(root: Path, window: Window) -> Path:
    return (
        root / "bronze" / "firms" / f"source={window.source}"
        / f"request_date={window.start:%Y-%m-%d}" / f"day_range={window.day_range}"
    )  # fmt: skip


def is_ingested(root: Path, window: Window) -> bool:
    """
    True if a bronze object already exists for this window.
    """
    base = _request_dir(root, window)
    return base.exists() and any(base.glob("ingested_at=*/manifest.json"))


def write_bronze(
    root: Path,
    window: Window,
    resp: FirmsResponse,
    bbox: tuple[float, float, float, float],
    ingested_at: datetime | None = None,
) -> Path:
    """
    Write `data.csv` (unchanged) and `manifest.json`; returns the prefix.
    """
    ts = ingested_at or datetime.now(UTC)
    prefix = _request_dir(root, window) / f"ingested_at={ts:%Y%m%dT%H%M%SZ}"
    prefix.mkdir(parents=True, exist_ok=False)
    tmp = prefix / "data.csv.tmp"
    tmp.write_bytes(resp.content)
    tmp.replace(prefix / "data.csv")
    manifest = {
        "source": window.source,
        "bbox": list(bbox),
        "day_range": window.day_range,
        "start_date": window.start.isoformat(),
        "requested_at": ts.isoformat(),
        "http_status": resp.status,
        "url": resp.url_redacted,
        "sha256": hashlib.sha256(resp.content).hexdigest(),
        "bytes": len(resp.content),
        "row_count": resp.row_count,
        "client_version": __version__,
    }
    (prefix / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return prefix
