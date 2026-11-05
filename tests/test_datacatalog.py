"""
Tests for table definitions.
"""

import polars as pl
import pytest

from firms_ua.datacatalog.base import Column, Table
from firms_ua.datacatalog.bronze import FirmsBronze
from firms_ua.errors import SchemaError


class Demo(Table):
    """
    Tiny table for tests.
    """

    name = "demo"
    layer = "silver"
    columns = (Column("a", pl.Int64, nullable=False), Column("b", pl.String))


def test_validate_ok() -> None:
    """
    A matching frame passes and the schema matches the definition.
    """
    Demo.validate(pl.DataFrame({"a": [1], "b": ["x"]}))
    assert Demo.schema() == pl.Schema({"a": pl.Int64, "b": pl.String})


@pytest.mark.parametrize(
    ("data", "fragment"),
    [
        ({"a": [1]}, "missing columns"),
        ({"a": [1], "b": ["x"], "c": [1]}, "unexpected columns"),
        ({"b": ["x"], "a": [1]}, "order"),
        ({"a": ["1"], "b": ["x"]}, "expected Int64"),
        ({"a": [None], "b": ["x"]}, "not nullable"),
    ],
)
def test_validate_failures(data: dict, fragment: str) -> None:
    """
    Each kind of mismatch is reported.
    """
    with pytest.raises(SchemaError, match=fragment):
        Demo.validate(pl.DataFrame(data, schema_overrides={"a": pl.Int64} if data.get("a") == [None] else None))


def test_bronze_definition() -> None:
    """
    Bronze raw columns are all strings and lineage comes after them.
    """
    assert all(c.dtype == pl.String for c in FirmsBronze.raw_columns)
    assert FirmsBronze.column_names()[-3:] == ["day_range", "start_date", "requested_at"]
