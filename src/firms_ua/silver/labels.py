"""
Explicit label tables: FIRMS codes to silver enums. An unknown code fails the run, so a new FIRMS label cannot slip through.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

import polars as pl

from firms_ua.common.errors import DataError
from firms_ua.common.sources import default_catalog

SATELLITES: Final = ("snpp", "noaa20", "noaa21")
PRODUCTS: Final = ("sp", "nrt")
CONFIDENCES: Final = ("low", "nominal", "high")
DAYNIGHTS: Final = ("day", "night")

SATELLITE: Final = pl.Enum(SATELLITES)
PRODUCT: Final = pl.Enum(PRODUCTS)
CONFIDENCE: Final = pl.Enum(CONFIDENCES)
DAYNIGHT: Final = pl.Enum(DAYNIGHTS)

# FIRMS source id -> (satellite, product), from the source catalog (the API's own `satellite` column is not used).
SOURCE_LABELS: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {source: (s.name, product) for s in default_catalog().values() for source, product in ((s.sp_source, "sp"), (s.nrt_source, "nrt"))}
)
# FIRMS `version` -> (product, collection). Seen in bronze: "2" (SP, collection 2) and "2.0NRT" (NRT, collection 2).
VERSION_LABELS: Final[Mapping[str, tuple[str, int]]] = MappingProxyType({"2": ("sp", 2), "2.0NRT": ("nrt", 2)})
CONFIDENCE_LABELS: Final[Mapping[str, str]] = MappingProxyType({"l": "low", "n": "nominal", "h": "high"})
DAYNIGHT_LABELS: Final[Mapping[str, str]] = MappingProxyType({"D": "day", "N": "night"})
# SP `type`: 0 presumed vegetation fire, 1 active volcano, 2 other static land source, 3 offshore.
TYPE_VALUES: Final = frozenset({"0", "1", "2", "3"})


def require_known(values: pl.Series, known: Mapping[str, object] | frozenset[str], what: str) -> None:
    """
    Fail if `values` holds a non-null label that is not in `known`.

    Raises:
        DataError: Naming the column and the unknown labels.
    """
    unknown = sorted(set(values.drop_nulls().unique().to_list()) - set(known))
    if unknown:
        msg = f"unknown {what} label(s): {unknown}; add them to firms_ua.silver.labels after checking the FIRMS docs"
        raise DataError(msg)
