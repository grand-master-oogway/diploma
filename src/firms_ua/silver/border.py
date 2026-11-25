"""
The Ukraine border: in or out, distance to it, and the buffer strip silver keeps outside it.

The boundary file is geoBoundaries gbOpen UKR ADM0 (simplified; see `boundary/README.md`): internationally recognised
borders, Crimea and the occupied territories included. Distances are computed in EPSG:3035 (Lambert azimuthal
equal-area for Europe), whose distortion over Ukraine is far below the 375 m pixel size.
"""

import hashlib
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl
import shapely
from pyproj import Transformer

BOUNDARY_PATH: Final = Path(__file__).parent / "boundary" / "ukraine_adm0.geojson"
BOUNDARY_NAME: Final = "geoBoundaries gbOpen UKR ADM0 UKR-ADM0-60985579 (simplified)"
METRIC_CRS: Final = "EPSG:3035"
_M_PER_KM: Final = 1000.0


@dataclass(frozen=True, slots=True, kw_only=True)
class Border:
    """
    The boundary polygon in metric coordinates, ready for vectorized queries, plus its lineage.
    """

    polygon: shapely.Polygon | shapely.MultiPolygon
    name: str
    sha256: str


def _to_metric(lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    transformer = Transformer.from_crs("EPSG:4326", METRIC_CRS, always_xy=True)
    x, y = transformer.transform(lon, lat)
    return np.asarray(x), np.asarray(y)


def read_border(path: Path, name: str) -> Border:
    """
    Load a single-feature GeoJSON boundary (lon/lat) and project it.
    """
    data = path.read_bytes()
    features = json.loads(data.decode("utf-8"))["features"]
    geometry = shapely.union_all([shapely.geometry.shape(f["geometry"]) for f in features])
    projected = shapely.transform(geometry, lambda xy: np.column_stack(_to_metric(xy[:, 0], xy[:, 1])))
    shapely.prepare(projected)
    return Border(polygon=projected, name=name, sha256=hashlib.sha256(data).hexdigest())


@cache
def default_border() -> Border:
    """
    Return the project's boundary (loaded once per process).
    """
    return read_border(BOUNDARY_PATH, BOUNDARY_NAME)


def locate(df: pl.DataFrame, border: Border) -> pl.DataFrame:
    """
    Add `in_ukraine` (Boolean) and `border_distance_km` (Float32, 0 inside) from `latitude` and `longitude`.
    """
    x, y = _to_metric(df["longitude"].to_numpy(), df["latitude"].to_numpy())
    points = shapely.points(x, y)
    inside = shapely.contains_xy(border.polygon, x, y)
    distance_km = np.where(inside, 0.0, shapely.distance(border.polygon, points) / _M_PER_KM) if df.height else np.empty(0)
    return df.with_columns(
        pl.Series("in_ukraine", inside, dtype=pl.Boolean),
        pl.Series("border_distance_km", distance_km, dtype=pl.Float32),
    )
