"""
Table definition primitives shared by all medallion layers.
"""

from dataclasses import dataclass
from typing import ClassVar

import polars as pl

from firms_ua.errors import SchemaError


@dataclass(frozen=True)
class Column:
    """
    One column of a table: name, Polars dtype and meaning.
    """

    name: str
    dtype: pl.DataType | type[pl.DataType]
    description: str = ""
    nullable: bool = True


class Table:
    """
    Base class for table definitions; subclasses only declare class attributes.

    Attributes:
        name: Table name.
        layer: Medallion layer (`bronze`, `silver` or `gold`).
        version: Bump when columns change.
        columns: Ordered column definitions.
        partition_by: Hive partition columns used when writing.
    """

    name: ClassVar[str]
    layer: ClassVar[str]
    version: ClassVar[int] = 1
    columns: ClassVar[tuple[Column, ...]] = ()
    partition_by: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def column_names(cls) -> list[str]:
        """
        Return column names in declared order.
        """
        return [c.name for c in cls.columns]

    @classmethod
    def schema(cls) -> pl.Schema:
        """
        Return the Polars schema for this table.
        """
        return pl.Schema({c.name: c.dtype for c in cls.columns})

    @classmethod
    def validate(cls, df: pl.DataFrame) -> None:
        """
        Check column names, order, dtypes and non-nullable columns.

        Raises:
            SchemaError: With a readable list of every mismatch.
        """
        problems: list[str] = []
        expected = cls.column_names()
        actual = df.columns
        missing = [c for c in expected if c not in actual]
        extra = [c for c in actual if c not in expected]
        if missing:
            problems.append(f"missing columns: {missing}")
        if extra:
            problems.append(f"unexpected columns: {extra}")
        if not missing and not extra and actual != expected:
            problems.append(f"column order differs: expected {expected}, got {actual}")
        for col in cls.columns:
            if col.name not in df.columns:
                continue
            if df.schema[col.name] != col.dtype:
                problems.append(f"{col.name}: expected {col.dtype}, got {df.schema[col.name]}")
            elif not col.nullable and df[col.name].null_count() > 0:
                problems.append(f"{col.name}: contains nulls but is not nullable")
        if problems:
            msg = f"{cls.layer}.{cls.name} schema mismatch: " + "; ".join(problems)
            raise SchemaError(msg)
