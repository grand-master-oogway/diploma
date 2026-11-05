"""
Bronze writer: FIRMS response -> string-typed Parquet, never overwritten.
"""

import io
import logging
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from firms_ua.datacatalog import FirmsBronze
from firms_ua.firms_client import FirmsResponse
from firms_ua.windows import Window

log = logging.getLogger(__name__)


def _source_dir(root: Path, window: Window) -> Path:
    return root / "bronze" / "firms" / f"source={window.source}"


def _stem(window: Window) -> str:
    return f"{window.start:%Y-%m-%d}_d{window.day_range}"


def is_ingested(root: Path, window: Window) -> bool:
    """
    True if a bronze file already exists for this window.
    """
    base = _source_dir(root, window)
    return base.exists() and any(base.glob(f"{_stem(window)}_*.parquet"))


def to_bronze_frame(content: bytes, window: Window, requested_at: datetime) -> pl.DataFrame:
    """
    Parse the API CSV with every column kept as a string and add lineage columns.

    Raises:
        SchemaError: If the CSV columns differ from the `FirmsBronze` definition.
    """
    df = pl.read_csv(io.BytesIO(content), infer_schema=False)
    df = df.with_columns(
        pl.lit(window.day_range, dtype=pl.Int16).alias("day_range"),
        pl.lit(window.start, dtype=pl.Date).alias("start_date"),
        pl.lit(requested_at, dtype=pl.Datetime("us", "UTC")).alias("requested_at"),
    )
    expected = FirmsBronze.column_names()
    if set(df.columns) == set(expected):
        df = df.select(expected)
    FirmsBronze.validate(df)
    return df


def write_bronze(root: Path, window: Window, resp: FirmsResponse, requested_at: datetime | None = None) -> Path:
    """
    Write one Parquet file for one response and return its path.

    Layout: `bronze/firms/source=<SOURCE>/<start>_d<days>_<UTC timestamp>.parquet`. A re-run adds a new file.
    """
    ts = requested_at or datetime.now(UTC)
    df = to_bronze_frame(resp.content, window, ts)

    directory = _source_dir(root, window)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{_stem(window)}_{ts:%Y%m%dT%H%M%S%fZ}.parquet"
    tmp = target.with_suffix(".parquet.tmp")
    df.write_parquet(tmp, compression="zstd")
    tmp.replace(target)
    log.info("bronze written: %s rows=%d", target, df.height)
    return target
