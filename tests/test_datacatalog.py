"""
Tests for the data catalog (core base class and concrete tables).
"""

import pandera.polars as pa
import polars as pl
import pytest

from firms_ua.datacatalog.bronze import FirmsBronze
from firms_ua.datacatalog_core.parquet_table import ParquetTable
from firms_ua.errors import SchemaError


class Demo(ParquetTable):
    """
    Tiny table for tests.
    """

    a: pl.Int64
    b: pl.String = pa.Field(nullable=True, metadata={"lineage": True})

    class Config:
        """
        Table name.
        """

        name = "silver.demo"
        metadata = {"version": 1, "partition_by": ("b",)}


GOOD = {"a": [1], "b": ["x"]}


def test_check_ok_and_helpers() -> None:
    """
    A matching frame passes; helpers reflect the declaration.
    """
    Demo.check(pl.DataFrame(GOOD))
    assert Demo.column_names() == ["a", "b"]
    assert Demo.polars_schema() == pl.Schema({"a": pl.Int64, "b": pl.String})
    assert Demo.columns_with_metadata("lineage") == ["b"]


@pytest.mark.parametrize(
    ("frame", "fragment"),
    [
        (pl.DataFrame({"a": [1]}), "'b' not in dataframe"),
        (pl.DataFrame({**GOOD, "c": [1]}), "column 'c' not in DataFrameSchema"),
        (pl.DataFrame({"b": ["x"], "a": [1]}), "out-of-order"),
        (pl.DataFrame({"a": ["1"], "b": ["x"]}), "expected column 'a' to have type Int64"),
        (pl.DataFrame({"a": [None], "b": ["x"]}, schema={"a": pl.Int64, "b": pl.String}), "non-nullable column 'a'"),
    ],
)
def test_check_failures(frame: pl.DataFrame, fragment: str) -> None:
    """
    Each kind of mismatch is reported through the project's SchemaError.
    """
    with pytest.raises(SchemaError, match=fragment):
        Demo.check(frame)


def test_bronze_definition() -> None:
    """
    Bronze API columns are strings; lineage and partition columns come last.
    """
    lineage = FirmsBronze.columns_with_metadata("lineage")
    assert lineage == ["day_range", "requested_at", "source", "start_date"]
    assert FirmsBronze.column_names()[-4:] == lineage
    assert FirmsBronze.partition_columns() == ["source", "acq_date"]
    assert FirmsBronze.file_columns() == [c for c in FirmsBronze.column_names() if c not in ("source", "acq_date")]
    schema = FirmsBronze.polars_schema()
    assert all(schema[c] == pl.String for c in schema.names() if c not in lineage)
    assert FirmsBronze.to_schema().name == "bronze.firms_viirs"
    assert FirmsBronze.table_version() == 1
