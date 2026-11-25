"""
H3 cells of detections: resolution 9 from the coordinates, resolution 7 as its parent.
"""

from typing import Final

import h3.api.basic_int as h3
import polars as pl

FINE_RES: Final = 9  # about 0.1 km2, close to one VIIRS I-band pixel: recurring sources, never published
COARSE_RES: Final = 7  # about 5.2 km2: the unit of gold aggregation


def _cells(points: pl.Series) -> pl.Series:
    return pl.Series(
        [h3.latlng_to_cell(p["latitude"], p["longitude"], FINE_RES) for p in points.to_list()],
        dtype=pl.UInt64,
    )


def _parents(cells: pl.Series) -> pl.Series:
    return pl.Series([h3.cell_to_parent(c, COARSE_RES) for c in cells.to_list()], dtype=pl.UInt64)


def add_cells(df: pl.DataFrame) -> pl.DataFrame:
    """
    Add `h3_r9` and `h3_r7` (UInt64 cell ids) from `latitude` and `longitude`.

    The coordinates are the pixel center, not the fire's location; the cell inherits that uncertainty.
    """
    return df.with_columns(
        pl.struct("latitude", "longitude").map_batches(_cells, return_dtype=pl.UInt64).alias("h3_r9"),
    ).with_columns(pl.col("h3_r9").map_batches(_parents, return_dtype=pl.UInt64).alias("h3_r7"))
