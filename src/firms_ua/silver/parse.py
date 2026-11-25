"""
Bronze strings -> typed columns: time, numbers, enums, ids. Any value that does not parse fails the run (never a null).
"""

import hashlib
from typing import Final

import polars as pl
from polars.exceptions import InvalidOperationError

from firms_ua.common.errors import DataError
from firms_ua.silver.labels import (
    CONFIDENCE,
    CONFIDENCE_LABELS,
    DAYNIGHT,
    DAYNIGHT_LABELS,
    PRODUCT,
    SATELLITE,
    SOURCE_LABELS,
    TYPE_VALUES,
    VERSION_LABELS,
    require_known,
)

KYIV_TZ: Final = "Europe/Kyiv"
UTC_DATETIME: Final = pl.Datetime("us", "UTC")
# FIRMS columns that must never be empty.
REQUIRED: Final = (
    "latitude",
    "longitude",
    "acq_date",
    "acq_time",
    "version",
    "confidence",
    "daynight",
    "bright_ti4",
    "bright_ti5",
    "frp",
    "scan",
    "track",
    "source",
)
_ID_SEPARATOR: Final = "|"
_ID_HEX_CHARS: Final = 32  # 128 bits of SHA-256: no collision risk at this data size


def _hash_ids(keys: pl.Series) -> pl.Series:
    """
    Return a stable hex id per key string (Polars' own hash is not guaranteed stable across versions).
    """
    return pl.Series([hashlib.sha256(k.encode()).hexdigest()[:_ID_HEX_CHARS] for k in keys.to_list()], dtype=pl.String)


def _check_labels_and_nulls(df: pl.DataFrame) -> None:
    for column in REQUIRED:
        nulls = df[column].null_count() + (df[column] == "").sum()
        if nulls:
            msg = f"{nulls} bronze rows have an empty `{column}`"
            raise DataError(msg)
    require_known(df["source"], SOURCE_LABELS, "source")
    require_known(df["version"], VERSION_LABELS, "version")
    require_known(df["confidence"], CONFIDENCE_LABELS, "confidence")
    require_known(df["daynight"], DAYNIGHT_LABELS, "daynight")
    require_known(df["type"], TYPE_VALUES, "type")
    if not df["acq_time"].str.contains(r"^\d{1,4}$").all():
        msg = "acq_time must be 1 to 4 digits (HHMM without leading zeros)"
        raise DataError(msg)


def parse_bronze(df: pl.DataFrame) -> pl.DataFrame:
    """
    Type a bronze frame (string FIRMS columns plus `source`, `requested_at` and the `acq_date` partition).

    `acq_time` is padded to four digits (`"58"` is 00:58) and combined with `acq_date` into one UTC timestamp;
    `acq_date_kyiv` is that instant's calendar date in Kyiv (daylight saving handled by the time-zone database).
    `detection_id` hashes the raw `source`, `latitude`, `longitude`, `acq_date` and padded `acq_time` strings, so the
    same detection in two responses gets the same id.

    Returns:
        One row per input row, columns `detection_id`, `acq_time`, `acq_date_kyiv`, `latitude`, `longitude`, `satellite`,
        `product`, `collection`, `bright_ti4`, `bright_ti5`, `frp`, `scan`, `track`, `pixel_area_km2`, `confidence`,
        `daynight`, `type`, `source`, `fetched_at`, `acq_date`.

    Raises:
        DataError: On an empty required value, an unknown label, a value that does not parse, or a `version` whose
            product disagrees with the `source`.
    """
    _check_labels_and_nulls(df)
    hhmm = pl.col("acq_time").str.zfill(4)
    try:
        out = df.select(
            pl.concat_str(["source", "latitude", "longitude", "acq_date", hhmm], separator=_ID_SEPARATOR)
            .map_batches(_hash_ids, return_dtype=pl.String)
            .alias("detection_id"),
            pl.concat_str(["acq_date", hhmm], separator=" ")
            .str.strptime(pl.Datetime("us"), "%Y-%m-%d %H%M", strict=True)
            .dt.replace_time_zone("UTC")
            .alias("acq_time"),
            pl.col("latitude").cast(pl.Float64, strict=True),
            pl.col("longitude").cast(pl.Float64, strict=True),
            pl.col("source").replace_strict({k: v[0] for k, v in SOURCE_LABELS.items()}, return_dtype=SATELLITE).alias("satellite"),
            pl.col("version").replace_strict({k: v[0] for k, v in VERSION_LABELS.items()}, return_dtype=PRODUCT).alias("product"),
            pl.col("version").replace_strict({k: v[1] for k, v in VERSION_LABELS.items()}, return_dtype=pl.Int8).alias("collection"),
            pl.col("source").replace_strict({k: v[1] for k, v in SOURCE_LABELS.items()}, return_dtype=PRODUCT).alias("_source_product"),
            *(pl.col(c).cast(pl.Float32, strict=True) for c in ("bright_ti4", "bright_ti5", "frp", "scan", "track")),
            pl.col("confidence").replace_strict(dict(CONFIDENCE_LABELS), return_dtype=CONFIDENCE),
            pl.col("daynight").replace_strict(dict(DAYNIGHT_LABELS), return_dtype=DAYNIGHT),
            pl.col("type").cast(pl.Int8, strict=True),
            pl.col("source"),
            pl.col("requested_at").alias("fetched_at"),
            pl.col("acq_date").str.to_date("%Y-%m-%d", strict=True),
        )
    except InvalidOperationError as err:
        msg = f"a bronze value does not parse: {err}"
        raise DataError(msg) from err
    mismatched = out.filter(pl.col("product") != pl.col("_source_product")).height
    if mismatched:
        msg = f"{mismatched} rows have a `version` whose product disagrees with their `source`"
        raise DataError(msg)
    return out.drop("_source_product").with_columns(
        pl.col("acq_time").dt.convert_time_zone(KYIV_TZ).dt.date().alias("acq_date_kyiv"),
        (pl.col("scan") * pl.col("track")).alias("pixel_area_km2"),
    )
