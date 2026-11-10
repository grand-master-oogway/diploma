"""
Bronze: raw FIRMS CSV -> string-typed Parquet in Hive partitions, never overwritten.
"""

import io
import logging
from datetime import datetime

import polars as pl

from firms_ua.datacatalog.bronze import FirmsBronze
from firms_ua.raw import RawObject, read_raw
from firms_ua.storage import Storage
from firms_ua.windows import Window

log = logging.getLogger(__name__)


def is_built(bronze: Storage, obj: RawObject) -> bool:
    """
    True if bronze already holds files built from this raw object (a response with zero rows writes none).
    """
    return FirmsBronze.part_exists(bronze, {"source": obj.window.source}, obj.requested_at)


def to_bronze_frame(content: bytes, window: Window, requested_at: datetime) -> pl.DataFrame:
    """
    Parse the API CSV with every column kept as a string and add the lineage columns (and a null `type` if absent).

    Raises:
        SchemaError: If the CSV columns differ from the `FirmsBronze` definition.
    """
    df = pl.read_csv(io.BytesIO(content), infer_schema=False)
    if "type" not in df.columns:  # only SP products carry it
        df = df.with_columns(pl.lit(None, dtype=pl.String).alias("type"))
    df = df.with_columns(
        pl.lit(window.day_range, dtype=pl.Int16).alias("day_range"),
        pl.lit(requested_at, dtype=pl.Datetime("us", "UTC")).alias("requested_at"),
        pl.lit(window.source, dtype=pl.String).alias("source"),
        pl.lit(window.start, dtype=pl.Date).alias("start_date"),
    )
    expected = FirmsBronze.column_names()
    if set(df.columns) == set(expected):
        df = df.select(expected)
    FirmsBronze.check(df)
    return df


def build_bronze(raw: Storage, bronze: Storage, obj: RawObject) -> list[str]:
    """
    Build bronze from one raw object and return the keys written, one file per acquisition date.

    The file names derive from the raw object's request time, so a raw object maps to one file per `acq_date`. Returns
    an empty list if it was already built or if the response has no rows (nothing to partition on).
    """
    if is_built(bronze, obj):
        log.info("skip %s: already in bronze", obj.key)
        return []
    df = to_bronze_frame(read_raw(raw, obj), obj.window, obj.requested_at)
    if df.is_empty():
        log.info("no rows in %s: nothing written to bronze", obj.key)
        return []
    keys = FirmsBronze.write(df, bronze, obj.requested_at)
    log.info("bronze built from %s: %d files, rows=%d", obj.key, len(keys), df.height)
    return keys
