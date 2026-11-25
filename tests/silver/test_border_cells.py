"""
Border location against the real boundary file, and H3 cells.
"""

import h3
import polars as pl
import pytest

from firms_ua.silver.border import default_border, locate
from firms_ua.silver.cells import add_cells

PLACES = {
    "Kyiv": (50.45, 30.52, True),
    "Simferopol": (44.95, 34.10, True),
    "Sevastopol": (44.60, 33.52, True),
    "Donetsk": (48.00, 37.80, True),
    "Luhansk": (48.57, 39.31, True),
    "Minsk": (53.90, 27.56, False),
    "Chisinau": (47.01, 28.86, False),
    "Black Sea gas field": (45.60, 31.20, False),
}


def frame(*points: tuple[float, float]) -> pl.DataFrame:
    """
    Return a frame of (latitude, longitude) points.
    """
    return pl.DataFrame({"latitude": [p[0] for p in points], "longitude": [p[1] for p in points]})


@pytest.mark.parametrize("name", PLACES)
def test_in_ukraine(name: str) -> None:
    """
    In ukraine.
    """
    lat, lon, inside = PLACES[name]
    out = locate(frame((lat, lon)), default_border())
    assert out["in_ukraine"].to_list() == [inside]
    assert (out["border_distance_km"][0] == 0) == inside


def test_distance_outside_is_in_km() -> None:
    # Moldova, about 10 km west of the Ukrainian border near Mohyliv-Podilskyi (border on the Dniester).
    """
    Distance outside is in km.
    """
    near = locate(frame((48.37, 27.70)), default_border())["border_distance_km"][0]
    minsk = locate(frame((53.90, 27.56)), default_border())["border_distance_km"][0]
    assert 2 < near < 20
    assert 220 < minsk < 260  # the border north of Rivne oblast lies about 2.1 degrees of latitude south of Minsk


def test_empty_frame() -> None:
    """
    Empty frame.
    """
    out = locate(frame(), default_border())
    assert out.height == 0
    assert out.schema["border_distance_km"] == pl.Float32


def test_cells_r9_and_parent_r7() -> None:
    """
    Cells r9 and parent r7.
    """
    out = add_cells(frame((50.45, 30.52)))
    r9 = h3.latlng_to_cell(50.45, 30.52, 9)
    assert out["h3_r9"].to_list() == [h3.str_to_int(r9)]
    assert out["h3_r7"].to_list() == [h3.str_to_int(h3.cell_to_parent(r9, 7))]
    assert out.schema["h3_r9"] == pl.UInt64


def test_default_border_lineage() -> None:
    """
    Default border lineage.
    """
    border = default_border()
    assert border.sha256 == "f30a4fabc64d72e67167f6627f778efdf49ed0af178030fc5b48be5d82682cfc"
